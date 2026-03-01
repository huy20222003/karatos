"""
Channel Base Module
Abstract base class for all communication channels.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional

from utils.logger import get_logger

logger = get_logger()

# Global Channel Manager Instance
_manager_instance: Optional["ChannelManager"] = None

def get_channel_manager() -> "ChannelManager":
    """Get the global channel manager instance"""
    global _manager_instance
    if _manager_instance is None:
        _manager_instance = ChannelManager()
    return _manager_instance

def get_channel(name: str) -> Optional["Channel"]:
    """Get a registered channel by name"""
    return get_channel_manager().get(name)


class MessageType(Enum):
    """Types of messages"""
    COMMAND = "command"       # User command like /status
    TEXT = "text"             # Regular text message
    CALLBACK = "callback"     # Button callback
    NOTIFICATION = "notification"  # Outgoing notification


@dataclass
class Message:
    """A message from any channel"""
    id: str
    channel: str              # 'telegram', 'internal', etc.
    type: MessageType
    content: str
    sender_id: Optional[str] = None
    sender_name: Optional[str] = None
    chat_id: Optional[str] = None
    reply_to: Optional[str] = None
    metadata: dict = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.utcnow)
    
    def is_command(self) -> bool:
        return self.type == MessageType.COMMAND or self.content.startswith("/")
        
    def get_command(self) -> Optional[str]:
        """Extract command name from message"""
        if self.content.startswith("/"):
            parts = self.content.split()
            full_cmd = parts[0][1:]  # Remove the /
            # Handle commands with bot suffix: /status@bot_username
            if "@" in full_cmd:
                return full_cmd.split("@")[0]
            return full_cmd
        return None
        
    def get_args(self) -> list[str]:
        """Get command arguments"""
        parts = self.content.split()
        return parts[1:] if len(parts) > 1 else []


class Channel(ABC):
    """
    Abstract base class for communication channels.
    
    To add a new channel:
    1. Create a new file in channels/
    2. Subclass Channel
    3. Implement receive() and send()
    """
    
    name: str = "base"
    is_connected: bool = False
    
    @abstractmethod
    async def connect(self) -> bool:
        """Connect to the channel"""
        pass
    
    @abstractmethod
    async def disconnect(self):
        """Disconnect from the channel"""
        pass
    
    @abstractmethod
    async def receive(self) -> list[Message]:
        """
        Receive pending messages from the channel.
        
        Returns:
            List of Message objects
        """
        pass
    
    @abstractmethod
    async def send(
        self,
        content: str,
        recipient: Optional[str] = None,
        reply_to: Optional[str] = None,
        **kwargs
    ) -> bool:
        """
        Send a message through the channel.
        
        Args:
            content: Message content
            recipient: Target chat/user ID
            reply_to: Message ID to reply to
            **kwargs: Channel-specific options
            
        Returns:
            True if sent successfully
        """
        pass
    
    async def send_notification(
        self,
        title: str,
        body: str,
        severity: str = "info",
        recipient: Optional[str] = None
    ) -> bool:
        """
        Send a formatted notification.
        
        Args:
            title: Notification title
            body: Notification body
            severity: 'info', 'warning', 'error', 'critical'
            recipient: Target (uses default if None)
        """
        emoji_map = {
            "info": "ℹ️",
            "warning": "⚠️",
            "error": "❌",
            "critical": "🚨"
        }
        emoji = emoji_map.get(severity, "📢")
        
        formatted = f"{emoji} <b>{title}</b>\n\n{body}"
        return await self.send(formatted, recipient=recipient, parse_mode="HTML")
        
    async def ask_confirmation(
        self,
        question: str,
        recipient: str,
        timeout: int = 300
    ) -> Optional[bool]:
        """
        Ask for confirmation (Yes/No).
        Override in subclasses that support interactive buttons.
        
        Returns:
            True/False based on user response, or None if timeout
        """
        # Default implementation: just send the question
        await self.send(f"❓ {question}\n\nReply with 'yes' or 'no'", recipient=recipient)
        return None  # Subclasses should implement actual confirmation logic


class ChannelManager:
    """
    Manages multiple communication channels.
    Provides unified interface for sending/receiving across all channels.
    """
    
    def __init__(self):
        self._channels: dict[str, Channel] = {}
        self._default_channel: Optional[str] = None
        
    def register(self, channel: Channel, is_default: bool = False):
        """Register a channel"""
        self._channels[channel.name] = channel
        if is_default or self._default_channel is None:
            self._default_channel = channel.name
        logger.info(f"[CHANNELS] Registered channel: {channel.name}")
        
    async def connect_all(self):
        """Connect all registered channels"""
        for name, channel in self._channels.items():
            try:
                if await channel.connect():
                    logger.info(f"[CHANNELS] Connected: {name}")
                else:
                    logger.warning(f"[CHANNELS] Failed to connect: {name}")
            except Exception as e:
                logger.error(f"[CHANNELS] Error connecting {name}: {e}")
                
    async def disconnect_all(self):
        """Disconnect all channels"""
        for channel in self._channels.values():
            try:
                await channel.disconnect()
            except Exception as e:
                logger.error(f"[CHANNELS] Error disconnecting: {e}")
                
    async def receive_all(self) -> list[Message]:
        """Receive messages from all channels"""
        all_messages = []
        
        for channel in self._channels.values():
            if channel.is_connected:
                try:
                    messages = await channel.receive()
                    all_messages.extend(messages)
                except Exception as e:
                    logger.error(f"[CHANNELS] Error receiving from {channel.name}: {e}")
                    
        return all_messages
        
    async def send(
        self,
        content: str,
        channel_name: Optional[str] = None,
        recipient: Optional[str] = None,
        **kwargs
    ) -> bool:
        """Send message through a specific channel or default"""
        target = channel_name or self._default_channel
        
        if not target or target not in self._channels:
            logger.warning(f"[CHANNELS] Channel not found: {target}")
            return False
            
        channel = self._channels[target]
        return await channel.send(content, recipient=recipient, **kwargs)
        
    async def broadcast(self, content: str, **kwargs) -> dict[str, bool]:
        """Send message to all channels"""
        results = {}
        
        for name, channel in self._channels.items():
            if channel.is_connected:
                try:
                    results[name] = await channel.send(content, **kwargs)
                except Exception as e:
                    logger.error(f"[CHANNELS] Broadcast error on {name}: {e}")
                    results[name] = False
                    
        return results
        
    def get(self, name: str) -> Optional[Channel]:
        """Get a channel by name"""
        return self._channels.get(name)
        
    def list_channels(self) -> list[dict]:
        """List all registered channels"""
        return [
            {
                "name": name,
                "connected": channel.is_connected,
                "is_default": name == self._default_channel
            }
            for name, channel in self._channels.items()
        ]
