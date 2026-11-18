# tests/test_config_instagram.py
from clipper.config import Config

def test_instagram_config_defaults():
    config = Config()
    assert hasattr(config, "instagram_username")
    assert hasattr(config, "instagram_password")
    assert hasattr(config, "instagram_session_file")
    assert hasattr(config, "instagram_db_path")
    assert hasattr(config, "instagram_caption_template")
    assert hasattr(config, "instagram_fallback_hashtags")
    assert hasattr(config, "instagram_max_hashtags")
    assert hasattr(config, "instagram_poll_interval_seconds")
    # Check defaults
    assert config.instagram_username == ""
    assert config.instagram_password == ""
    assert config.instagram_session_file == "session.json"
    assert config.instagram_db_path == "clips.db"
    assert config.instagram_max_hashtags == 30
    assert config.instagram_poll_interval_seconds == 30

def test_instagram_config_from_yaml(tmp_path):
    yaml_path = tmp_path / "config.yaml"
    yaml_content = '''
instagram:
  username: "testuser"
  session_file: "custom_session.json"
  db_path: "custom.db"
  caption_template: "Custom: {top_phrase}"
  fallback_hashtags: ["custom"]
  max_hashtags: 10
  poll_interval_seconds: 60
'''
    yaml_path.write_text(yaml_content)
    config = Config.load(str(yaml_path))
    assert config.instagram_username == "testuser"
    assert config.instagram_session_file == "custom_session.json"
    assert config.instagram_db_path == "custom.db"
    assert config.instagram_caption_template == "Custom: {top_phrase}"
    assert config.instagram_fallback_hashtags == ["custom"]
    assert config.instagram_max_hashtags == 10
    assert config.instagram_poll_interval_seconds == 60

def test_instagram_config_from_cli():
    config, url = Config.from_args([
        "--ig-username", "cliuser",
        "--ig-session", "cli_session.json",
        "--ig-db", "cli.db",
        "--ig-poll-interval", "45"
    ])
    assert config.instagram_username == "cliuser"
    assert config.instagram_session_file == "cli_session.json"
    assert config.instagram_db_path == "cli.db"
    assert config.instagram_poll_interval_seconds == 45