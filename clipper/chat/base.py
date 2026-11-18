from dataclasses import dataclass
from typing import AsyncIterator

@dataclass
class ChatMessage:
    timestamp: float  # Epoch seconds
    user: str
    text: str

class ChatSource:
    async def connect(self, channel: str):
        pass
    
    async def messages(self) -> AsyncIterator[ChatMessage]:
        if False: yield ChatMessage(0, "", "") # Type hint helper
    
    async def close(self):
        pass
