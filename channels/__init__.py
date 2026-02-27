"""
Channels Package
Multi-channel I/O for Agent communication.
"""
from channels.base import Channel, Message
from channels.telegram import TelegramChannel

__all__ = [
    "Channel",
    "Message",
    "TelegramChannel"
]
