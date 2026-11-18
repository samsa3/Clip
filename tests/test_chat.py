import pytest
from clipper.chat.twitch import TwitchChat
import asyncio

@pytest.mark.asyncio
async def test_twitch_irc_parser():
    # Test message with tmi-sent-ts
    raw = "@badge-info=;badges=;client-nonce=x;color=;display-name=User;emotes=;first-msg=0;flags=;id=1;mod=0;returning-chatter=0;room-id=2;subscriber=0;tmi-sent-ts=1700000000000;turbo=0;user-id=3;user-type= :user!user@user.tmi.twitch.tv PRIVMSG #channel :Hello world"
    chat = TwitchChat()
    msg = chat._parse_irc_line(raw)
    assert msg is not None
    assert msg.text == "Hello world"
    assert msg.user == "User"
    assert msg.timestamp == 1700000000.0

