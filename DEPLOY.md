# Deploying Clipper to Oracle Cloud Free Tier (ARM)

## Overview

This guide covers deploying the Clipper live-stream auto-clipper with Instagram Reels upload to an Oracle Cloud Free Tier ARM instance (Ampere A1 Flex, 4 OCPU, 24 GB RAM) running Ubuntu 24.04.

## Prerequisites

- Oracle Cloud account with Free Tier eligibility
- SSH key pair for instance access
- Instagram Creator/Business account (for Reels posting)

---

## 1. Oracle Instance Setup

### Create Instance

1. Log in to Oracle Cloud Console
2. Navigate to **Compute → Instances → Create Instance**
3. Configure:
   - **Name**: `clipper-arm`
   - **Compartment**: your compartment
   - **Placement**: Choose any available AD
   - **Image**: Ubuntu 24.04 Minimal (ARM)
   - **Shape**: `VM.Standard.A1.Flex` (Ampere ARM)
   - **OCPUs**: 4 (max free tier)
   - **Memory**: 24 GB (max free tier)
   - **Boot volume**: 200 GB (free tier includes 200 GB total)
   - **SSH keys**: Paste your public key
   - **Networking**: Create new VCN with public subnet, assign public IP

4. Click **Create** and wait for instance to be **Running**

### Configure Security Lists / Network Security Groups

Allow inbound:
- **SSH (22)**: Your IP or 0.0.0.0/0 (restrict in production)
- **HTTP (80)**: Optional, for health checks
- **HTTPS (443)**: Optional

---

## 2. Server Initialization

```bash
# SSH into instance
ssh ubuntu@<PUBLIC_IP>

# Update system
sudo apt update && sudo apt upgrade -y

# Install dependencies
sudo apt install -y python3.12 python3.12-venv python3.12-dev \
    ffmpeg git sqlite3 curl htop

# Verify ffmpeg
ffmpeg -version
ffprobe -version
```

### Create clipper user and directories

```bash
# Create dedicated user (no shell login)
sudo useradd -r -s /bin/bash -d /opt/clipper -m clipper

# Create directory structure
sudo mkdir -p /opt/clipper/{clips,logs,buffer}
sudo chown -R clipper:clipper /opt/clipper
sudo chmod 750 /opt/clipper
sudo chmod 770 /opt/clipper/clips /opt/clipper/logs /opt/clipper/buffer
```

---

## 3. Application Deployment

### Clone repository

```bash
sudo -u clipper git clone https://github.com/yourusername/Clip.git /opt/clipper/app
cd /opt/clipper/app
```

### Create virtual environment and install

```bash
sudo -u clipper python3.12 -m venv /opt/clipper/.venv
sudo -u clipper /opt/clipper/.venv/bin/pip install --upgrade pip
sudo -u clipper /opt/clipper/.venv/bin/pip install -r requirements.txt
sudo -u clipper /opt/clipper/.venv/bin/pip install -e .
```

### Configure secrets

Create `/etc/clipper/secrets.env` with **600 permissions**:

```bash
sudo mkdir -p /etc/clipper
sudo tee /etc/clipper/secrets.env > /dev/null <<'EOF'
# Instagram credentials (keep secure!)
INSTAGRAM_USERNAME=your_ig_username
INSTAGRAM_PASSWORD=your_ig_password
EOF

sudo chown root:clipper /etc/clipper/secrets.env
sudo chmod 640 /etc/clipper/secrets.env
```

### Create config.yaml

```bash
sudo -u clipper tee /opt/clipper/config.yaml > /dev/null <<'EOF'
# Clipper config
output_dir: "/opt/clipper/clips"
max_clips: 50
buffer_seconds: 60
segment_seconds: 5
fire_score: 55
threshold: 3.0

# Instagram config
instagram:
  username: ""  # Filled from secrets.env at runtime
  password: ""  # Filled from secrets.env at runtime
  session_file: "/opt/clipper/session.json"
  db_path: "/opt/clipper/clips.db"
  caption_template: "{top_phrase} 🔥 score: {score:.0f} | {chat_sample}\n\n{hashtags}"
  fallback_hashtags: ["twitch", "clips", "gaming", "reels", "viral"]
  max_hashtags: 30
  poll_interval_seconds: 30
EOF

sudo chown clipper:clipper /opt/clipper/config.yaml
```

---

## 4. Instagram Authentication (One-Time)

The `instagrapi` library handles 2FA challenges interactively. Run once manually on the server:

```bash
# Switch to clipper user
sudo -u clipper -i

# Load secrets
source /etc/clipper/secrets.env

# Run interactive login (will prompt for 2FA code)
cd /opt/clipper/app
/opt/clipper/.venv/bin/python -c "
from instagrapi import Client
cl = Client()
cl.login('$INSTAGRAM_USERNAME', '$INSTAGRAM_PASSWORD')
cl.dump_settings('/opt/clipper/session.json')
print('Session saved!')
"
```

This creates `/opt/clipper/session.json` which the daemon will reuse. **Do this once**; subsequent runs use the session file.

---

## 5. Systemd Service

### Install service file

```bash
sudo cp /opt/clipper/app/systemd/clipper-upload.service /etc/systemd/system/
sudo systemctl daemon-reload
```

### Enable and start

```bash
sudo systemctl enable clipper-upload
sudo systemctl start clipper-upload

# Check status
sudo systemctl status clipper-upload
sudo journalctl -u clipper-upload -f
```

---

## 6. Log Rotation

Create `/etc/logrotate.d/clipper`:

```bash
sudo tee /etc/logrotate.d/clipper > /dev/null <<'EOF'
/opt/clipper/logs/*.log {
    daily
    rotate 14
    compress
    delaycompress
    missingok
    notifempty
    create 640 clipper clipper
}
EOF
```

---

## 7. Database Backup (Daily)

Create `/opt/clipper/backup_db.sh`:

```bash
#!/bin/bash
set -euo pipefail
DATE=$(date +%F)
cp /opt/clipper/clips.db /opt/clipper/backups/clips_${DATE}.db
find /opt/clipper/backups -name "clips_*.db" -mtime +30 -delete
```

```bash
sudo -u clipper mkdir -p /opt/clipper/backups
sudo chmod +x /opt/clipper/backup_db.sh
```

Add to clipper user's crontab:

```bash
sudo -u clipper crontab -e
# Add:
0 3 * * * /opt/clipper/backup_db.sh
```

### Off-site backup (optional but recommended)

```bash
# From your local machine, daily pull:
scp -i ~/.ssh/oracle_key ubuntu@<PUBLIC_IP>:/opt/clipper/backups/*.db ./backups/
```

---

## 8. Monitoring & Health Checks

### Check daemon health

```bash
# Service status
sudo systemctl status clipper-upload

# Recent logs
sudo journalctl -u clipper-upload --since "1 hour ago"

# Database stats
sudo -u clipper /opt/clipper/.venv/bin/python -c "
import sqlite3
conn = sqlite3.connect('/opt/clipper/clips.db')
c = conn.cursor()
c.execute('SELECT COUNT(*) FROM clips')
print(f'Total clips: {c.fetchone()[0]}')
c.execute('SELECT COUNT(*) FROM clips WHERE uploaded_at IS NOT NULL')
print(f'Uploaded: {c.fetchone()[0]}')
c.execute('SELECT COUNT(*) FROM clips WHERE uploaded_at IS NULL')
print(f'Pending: {c.fetchone()[0]}')
c.execute('SELECT COUNT(*) FROM clips WHERE error IS NOT NULL')
print(f'Failed: {c.fetchone()[0]}')
"
```

### Prometheus metrics (optional)

Add to daemon if needed; not included by default.

---

## 9. Updating the Application

```bash
cd /opt/clipper/app
sudo -u clipper git pull
sudo -u clipper /opt/clipper/.venv/bin/pip install -e .
sudo systemctl restart clipper-upload
```

---

## 10. Troubleshooting

| Issue | Solution |
|-------|----------|
| `instagrapi` ChallengeRequired | Re-run manual login (step 4); session may have expired |
| `PleaseWaitFewMinutes` | Rate limit hit; wait or increase `poll_interval_seconds` |
| `LoginRequired` | Session expired; re-run manual login |
| No clips uploading | Check `journalctl -u clipper-upload` for errors; verify `clips/` has new MP4s |
| Disk full | Check `/opt/clipper/clips` rotation; `max_clips` in config |
| `ffprobe` not found | Install `ffmpeg` package |

---

## 11. Security Checklist

- [ ] Secrets file is `640 root:clipper`
- [ ] Clipper user has no sudo access
- [ ] SSH key-only login (disable password auth)
- [ ] Firewall/NSG restricts SSH to your IP
- [ ] Systemd service runs as non-root `clipper` user
- [ ] Database backups encrypted if stored off-site
- [ ] Regular `apt upgrade` scheduled

---

## 12. Architecture Summary

```
┌─────────────────────────────────────────────────────────────┐
│  Oracle ARM Instance (4 OCPU, 24 GB RAM)                   │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  clipper-upload.service (systemd)                   │   │
│  │  └─ asyncio daemon (poll every 30s)                 │   │
│  │       ├─ InstagramUploader (instagrapi)             │   │
│  │       │   ├─ login() → session.json                 │   │
│  │       │   ├─ process_pending()                      │   │
│  │       │   │   ├─ validate_reels_spec() (ffprobe)    │   │
│  │       │   │   ├─ generate_caption()                 │   │
│  │       │   │   └─ clip_upload() → Reels              │   │
│  │       │   └─ rate limit: 25/day, 1/min burst        │   │
│  │       └─ SQLite (clips.db, WAL mode)                │   │
│  └─────────────────────────────────────────────────────┘   │
│  ┌─────────────────┐  ┌─────────────────┐                  │
│  │  clips/         │  │  buffer/        │                  │
│  │  clip_*.mp4     │  │  seg_*.ts       │                  │
│  │  clip_*.json    │  │                 │                  │
│  └─────────────────┘  └─────────────────┘                  │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  clips.db (SQLite)                                  │   │
│  │  clips table: id, file_path, meta_path,             │   │
│  │    uploaded_at, instagram_id, caption,              │   │
│  │    error, attempts, created_at                      │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

---

## 13. Cost

**$0/month** — Oracle Cloud Free Tier includes:
- 2x AMD VMs (1 OCPU, 6 GB) OR 1x ARM VM (4 OCPU, 24 GB)
- 200 GB block storage
- 10 TB/month network egress

The ARM instance specified here fits entirely within the Always Free tier.

---

## License

MIT — see LICENSE in repository root.