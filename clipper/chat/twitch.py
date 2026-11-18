import asyncio
import websockets
import time
import logging
from clipper.chat.base import ChatSource, ChatMessage

logger = logging.getLogger(__name__)

class TwitchChat(ChatSource):
    def __init__(self):
        self.ws = None
        self.queue = asyncio.Queue()

    async def connect(self, channel: str):
        url = "wss://irc-ws.chat.twitch.tv:443"
        self.ws = await websockets.connect(url)
        await self.ws.send("CAP REQ :twitch.tv/tags")
        await self.ws.send("PASS SCHMOOPIE")
        await self.ws.send(f"NICK justinfan{int(time.time()) % 100000}")
        await self.ws.send(f"JOIN #{channel.lower()}")
        asyncio.create_task(self._listen())

    async def _listen(self):
        try:
            async for line in self.ws:
                if line.startswith("PING"):
                    await self.ws.send("PONG :tmi.twitch.tv")
                    continue
                
                msg = self._parse_irc_line(line)
                if msg:
                    await self.queue.put(msg)
        except Exception as e:
            logger.error(f"Twitch chat error: {e}")

    def _parse_irc_line(self, line: str) -> ChatMessage:
        if "PRIVMSG" not in line:
            return None
        
        tags = {}
        if line.startswith("@"):
            tag_part, rest = line[1:].split(" ", 1)
            for t in tag_part.split(";"):
                if "=" in t:
                    k, v = t.split("=", 1)
                    tags[k] = v
        
        # User and message
        # :user!user@user.tmi.twitch.tv PRIVMSG #channel :message
        try:
            parts = line.split(" PRIVMSG #", 1)
            user_part = parts[0].split(":")[-1].split("!")[0]
            if "display-name" in tags and tags["display-name"]:
                user = tags["display-name"]
            else:
                user = user_part
            
            text = parts[1].split(" :", 1)[1].strip()
            
            ts = time.time()
            if "tmi-sent-ts" in tags:
                ts = int(tags["tmi-sent-ts"]) / 1000.0
            
            return ChatMessage(timestamp=ts, user=user, text=text)
        except Exception:
            return None

    async def messages(self):
        while True:
            yield await self.queue.get()

    async def close(self):
        if self.ws:
            await self.ws.close()
