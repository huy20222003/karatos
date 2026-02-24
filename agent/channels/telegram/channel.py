"""
Telegram Channel
Core API interactions for the Telegram channel.
"""
import asyncio
import aiohttp
import re
import json
from typing import Optional, Any, Union
from datetime import datetime

from config.settings import settings
from utils.logger import get_logger
from ..base import Channel, Message, MessageType

logger = get_logger()

# Singleton instance - keeping for compatibility but preferring ChannelManager
from ..base import get_channel_manager

def get_telegram_channel() -> Optional["TelegramChannel"]:
    """Get the active Telegram channel instance"""
    from ..base import get_channel
    return get_channel("telegram")


class TelegramChannel(Channel):
    """
    Telegram Bot channel for Brain.
    """
    
    name = "telegram"
    
    # Bot API base URL
    API_BASE = "https://api.telegram.org/bot{token}"
    
    # Available commands
    COMMANDS = {
        "help": "Show available commands",
        "status": "Show agent status",
        "queue": "Show current action queue status",
        "cancel": "Cancel a pending queue action (usage: /cancel <id>)",
        "health": "Check system health",
        "services": "Show service monitoring details",
        "patrol": "Trigger a patrol cycle",
        "history": "Show recent decisions",
        "memory": "Show memory statistics",
        "clearcache": "Clear Semantic Cache (Purge bad memories)",
        "clearcache": "Clear Semantic Cache (Purge bad memories)",
        "addmcp": "Add or update an MCP server",
        "listmcp": "List all configured MCP servers"
    }
    
    def __init__(self, token: Optional[str] = None, admin_chat_id: Optional[str] = None):
        self.token = token or getattr(settings, 'telegram_bot_token', None)
        self.admin_chat_id = admin_chat_id or getattr(settings, 'telegram_admin_chat_id', None)
        self.username: Optional[str] = None
        self.bot_id: Optional[str] = None
        self.is_connected = False
        self._last_update_id = 0
        self._session: Optional[aiohttp.ClientSession] = None
        
    @property
    def api_url(self) -> str:
        return self.API_BASE.format(token=self.token)
        
    async def connect(self) -> bool:
        """Connect to Telegram Bot API"""
        if not self.token:
            logger.warning("[TELEGRAM] No bot token configured")
            return False
            
        try:
            self._session = aiohttp.ClientSession()
            
            # Test connection by getting bot info
            result = await self._api_call("getMe")
            
            if result.get("ok"):
                bot_info = result.get("result", {})
                self.is_connected = True
                
                # Dynamic Identity Update
                first_name = bot_info.get('first_name')
                if first_name:
                    self.username = bot_info.get('username')
                    self.bot_id = str(bot_info.get('id'))
                    logger.info(f"[TELEGRAM] Connected as @{self.username} ('{first_name}')")
                    from config.settings import settings
                    settings.bot_name = first_name
                    # Store username in settings too for easy access
                    settings.bot_username = self.username
                
                # Register with global ChannelManager
                get_channel_manager().register(self)
                
                # Set commands menu
                await self._set_commands()
                
                # WARMUP: Get latest update_id to skip old messages
                warmup = await self._api_call("getUpdates", {"offset": -1, "limit": 1})
                if warmup.get("ok") and warmup.get("result"):
                    self._last_update_id = warmup["result"][0]["update_id"]
                    logger.info(f"[TELEGRAM] Warmup complete. Skipping old messages (Last ID: {self._last_update_id})")
                
                return True
            else:
                logger.error(f"[TELEGRAM] Connection failed: {result}")
                return False
                
        except Exception as e:
            logger.error(f"[TELEGRAM] Connection error: {e}")
            return False
            
    async def disconnect(self):
        """Disconnect from Telegram"""
        if self._session:
            await self._session.close()
            self._session = None
        self.is_connected = False
        logger.info("[TELEGRAM] Disconnected")
        
    async def start(self, handler: Optional[Any] = None):
        """
        Infinite polling loop for Telegram updates.
        This matches the requirement of TelegramConnector.
        """
        if handler:
            if not hasattr(self, 'handlers'):
                self.handlers = []
            if handler not in self.handlers:
                self.handlers.append(handler)

        if not self.is_connected:
            if not await self.connect():
                return
                
        logger.info("[TELEGRAM] Starting polling loop...")
        while self.is_connected:
            try:
                messages = await self.receive()
                
                for msg in messages:
                    if hasattr(self, 'handlers'):
                        for handler in self.handlers:
                            # Non-blocking: process each message concurrently
                            # This prevents one slow LLM call from blocking the entire polling loop
                            asyncio.create_task(self._safe_handle(handler, msg))
                            
                await asyncio.sleep(0.5)
            except Exception as e:
                logger.error(f"[TELEGRAM] Polling error: {e}")
                await asyncio.sleep(5)

    async def _safe_handle(self, handler, msg):
        """Wrapper to safely run a message handler as a background task."""
        try:
            await handler(msg)
        except Exception as e:
            logger.error(f"[TELEGRAM] Handler error for message {msg.id}: {e}")
        
    async def receive(self) -> list[Message]:
        """
        Poll for new messages using getUpdates.
        Returns list of Message objects.
        """
        if not self.is_connected:
            return []
            
        messages = []
        
        try:
            result = await self._api_call("getUpdates", {
                "offset": self._last_update_id + 1,
                "timeout": 1,  # Short poll
                "allowed_updates": ["message", "callback_query"]
            })
            
            if not result.get("ok"):
                return []
                
            updates = result.get("result", [])
            
            for update in updates:
                self._last_update_id = update["update_id"]
                
                # Handle regular messages
                if "message" in update:
                    msg = update["message"]
                    # Skip messages from THIS bot (prevent self-loop in groups)
                    sender_id = str(msg.get("from", {}).get("id", ""))
                    if self.bot_id and sender_id == self.bot_id:
                        continue
                    messages.append(self._parse_message(msg))
                    
                # Handle callback queries
                elif "callback_query" in update:
                    callback = update["callback_query"]
                    messages.append(self._parse_callback(callback))
                    
        except Exception as e:
            logger.error(f"[TELEGRAM] Error receiving messages: {e}")
            
        return messages
        
    async def send(
        self,
        content: Union[str, dict],
        recipient: Optional[str] = None,
        reply_to: Optional[str] = None,
        parse_mode: str = "Markdown",
        **kwargs
    ) -> bool:
        """Send a message via Telegram. Supports both text and structured dicts with photos."""
        chat_id = recipient or self.admin_chat_id
        if not chat_id: return False

        # Handle structured response with photo
        if isinstance(content, dict) and content.get("photo"):
            logger.info(f"[TELEGRAM] Sending structured response with photo to {chat_id}")
            photo_bytes = content.get("photo")
            if isinstance(photo_bytes, bytes):
                return await self.send_photo(
                    photo_bytes=photo_bytes,
                    caption=content.get("caption") or content.get("text", ""),
                    recipient=chat_id,
                    parse_mode=parse_mode
                )
            content = content.get("text", str(content))

        # Basic text content
        text_to_send = content
        if isinstance(content, dict):
            text_to_send = content.get("text", str(content))

        # Normalize LLM markdown (GitHub-style) to Telegram V1
        if parse_mode == "Markdown":
            text_to_send = self.normalize_markdown(text_to_send)

        # Smart underscore escaping: Only escape bare underscores that break Telegram V1 parser
        # Do NOT escape *, `, [ — those are intentional markdown formatting
        safe_text = text_to_send
        if parse_mode == "Markdown" and "_" in text_to_send:
            safe_text = self._escape_underscores(text_to_send)

        try:
            params = {
                "chat_id": chat_id,
                "text": safe_text,
                "parse_mode": parse_mode
            }
            
            # Defensive check for empty text
            if not safe_text or str(safe_text).strip() == "":
                logger.warning(f"[TELEGRAM] Attempted to send empty message to {chat_id}. Using fallback.")
                params["text"] = "⚠️ System Alert: An error occurred while preparing this response. Please try again or check system logs."
            
            if reply_to:
                params["reply_to_message_id"] = reply_to
                
            if "keyboard" in kwargs:
                params["reply_markup"] = json.dumps(kwargs["keyboard"])
                
            result = await self._api_call("sendMessage", params)
            
            if result.get("ok"):
                logger.debug(f"[TELEGRAM] Message sent to {chat_id}")
                return True
            else:
                desc = result.get("description", "").lower()
                if "entities" in desc or "parse_mode" in desc:
                    logger.debug(f"[TELEGRAM] Markdown parsing failed ({desc}). Retrying with escaped text.")
                    params["text"] = self.escape_markdown(text_to_send)
                    result = await self._api_call("sendMessage", params)
                    if result.get("ok"):
                        return True
                    
                    # Final fallback: NO parse_mode
                    logger.warning("[TELEGRAM] Escaped markdown also failed for send. Falling back to plain text.")
                    params.pop("parse_mode", None)
                    params["text"] = text_to_send
                    result = await self._api_call("sendMessage", params)
                    return result.get("ok", False)
                
                logger.error(f"[TELEGRAM] Failed to send: {result}")
                
                # Safe check for prefix on potentially dict content
                text_content = str(content) if not isinstance(content, str) else content
                if not text_content.startswith("⚠️"):
                    await self._api_call("sendMessage", {
                    "chat_id": chat_id,
                    "text": "⚠️ System Alert: An error occurred while formatting this message. Please check system logs.",
                    "parse_mode": "Markdown"
                })
                return False
                
        except Exception as e:
            logger.error(f"[TELEGRAM] Send error: {e}")
            return False

    async def send_photo(
        self,
        photo_bytes: bytes,
        caption: str = "",
        recipient: Optional[str] = None,
        parse_mode: str = "Markdown"
    ) -> bool:
        """Send a photo via Telegram"""
        chat_id = recipient or self.admin_chat_id
        if not chat_id: return False

        # Normalize LLM markdown and escape special characters intelligently
        safe_caption = caption
        if parse_mode == "Markdown":
             safe_caption = self.normalize_markdown(safe_caption)
             if "_" in safe_caption:
                 safe_caption = self._escape_underscores(safe_caption)

        try:
            url = f"{self.api_url}/sendPhoto"
            data = aiohttp.FormData()
            data.add_field('chat_id', str(chat_id))
            data.add_field('photo', photo_bytes, filename='chart.png', content_type='image/png')
            if safe_caption:
                # Telegram Caption Limit is 1024 chars
                if len(safe_caption) > 1024:
                    safe_caption = safe_caption[:1021] + "..."
                data.add_field('caption', safe_caption)
                data.add_field('parse_mode', parse_mode)

            async with self._session.post(url, data=data) as response:
                result = await response.json()
                
                if result.get("ok"):
                    return True
                else:
                    # Retry logic for Markdown errors
                    desc = result.get("description", "").lower()
                    if "parse_mode" in desc or "entities" in desc:
                        logger.debug(f"[TELEGRAM] Photo caption markdown failed ({desc}). Retrying with escaped text.")
                        
                        # Re-create FormData and try with fully escaped text
                        data = aiohttp.FormData()
                        data.add_field('chat_id', str(chat_id))
                        data.add_field('photo', photo_bytes, filename='chart.png', content_type='image/png')
                        data.add_field('caption', self.escape_markdown(caption)) 
                        data.add_field('parse_mode', "Markdown")
                        
                        async with self._session.post(url, data=data) as retry_resp:
                            retry_result = await retry_resp.json()
                            if retry_result.get("ok"):
                                return True
                                
                            # If still failing, try NO parse_mode at all
                            logger.warning("[TELEGRAM] Escaped markdown also failed. Falling back to plain text.")
                            data = aiohttp.FormData()
                            data.add_field('chat_id', str(chat_id))
                            data.add_field('photo', photo_bytes, filename='chart.png', content_type='image/png')
                            data.add_field('caption', caption)
                            async with self._session.post(url, data=data) as final_resp:
                                final_res = await final_resp.json()
                                return final_res.get("ok", False)
                            
                    logger.error(f"[TELEGRAM] Failed to send photo: {result}")
                    return False

        except Exception as e:
            logger.error(f"[TELEGRAM] Send photo error: {e}")
            return False
            
    def normalize_markdown(self, text: str) -> str:
        """Convert GitHub/ChatGPT-style markdown to Telegram V1 Markdown.
        
        Key conversions:
        - **bold** → *bold* (Telegram V1 bold is single asterisk)
        - ### heading → *heading* (Telegram has no heading, use bold)
        - - list → • list
        - Preserves `code`, ```blocks```, and *italic* (single asterisk stays as-is after conversion)
        """
        if not text: return text
        
        # 1. Protect code blocks first (replace with placeholders)
        code_blocks = []
        def save_code_block(match):
            code_blocks.append(match.group(0))
            return f"__CODE_BLOCK_{len(code_blocks)-1}__"
        
        # Multi-line code blocks
        text = re.sub(r'```[\s\S]*?```', save_code_block, text)
        # Inline code
        text = re.sub(r'`[^`]+`', save_code_block, text)
        
        # 2. Convert ### headings to bold
        text = re.sub(r'^#{1,6}\s+(.+)$', r'*\1*', text, flags=re.MULTILINE)
        
        # 3. Convert **bold** to *bold* (Telegram V1)
        text = re.sub(r'\*\*(.+?)\*\*', r'*\1*', text)
        
        # 4. Convert bullet lists to use bullet character
        text = re.sub(r'^(\s*)[-*]\s+', r'\1• ', text, flags=re.MULTILINE)
        
        # 5. Restore code blocks
        for i, block in enumerate(code_blocks):
            text = text.replace(f"__CODE_BLOCK_{i}__", block)
        
        return text

    def escape_markdown(self, text: str) -> str:
        """Escape ALL special characters for Telegram Markdown (V1) — used as last resort fallback."""
        if not text: return ""
        return text.replace("_", "\\_").replace("*", "\\*").replace("`", "\\`").replace("[", "\\[")

    def _escape_underscores(self, text: str) -> str:
        """Escape only underscores that are NOT part of _italic_ markdown.
        Preserves intentional formatting while fixing technical strings like variable_names."""
        if not text: return ""
        import re as _re
        
        # 1. Protect @usernames first so they don't get matched as italics
        # We replace them with a placeholder, then restore
        usernames = []
        def save_username(match):
            usernames.append(match.group(0).replace("_", "\\_"))
            return f"@@USERNAME{len(usernames)-1}@@"
            
        text = _re.sub(r'@[a-zA-Z0-9_]+', save_username, text)
        
        # 2. Protect _italic_ pairs
        parts = []
        last_end = 0
        for match in _re.finditer(r'_([^_]+)_', text):
            # Escape bare underscores before this italic
            before = text[last_end:match.start()].replace("_", "\\_")
            parts.append(before)
            parts.append(match.group(0))  # Keep _italic_ as-is
            last_end = match.end()
            
        # 3. Escape remaining underscores after last italic
        parts.append(text[last_end:].replace("_", "\\_"))
        text = "".join(parts)
        
        # 4. Restore usernames
        for i, uname in enumerate(usernames):
            text = text.replace(f"@@USERNAME{i}@@", uname)
            
        return text
            
    async def send_notification(
        self,
        title: str,
        body: str,
        severity: str = "info",
        recipient: Optional[str] = None
    ) -> bool:
        """Send a formatted notification"""
        emoji_map = {
            "info": "ℹ️",
            "warning": "⚠️",
            "error": "❌",
            "critical": "🚨",
            "success": "✅"
        }
        emoji = emoji_map.get(severity, "📢")
        formatted = f"{emoji} *{title}*\n\n{body}"
        return await self.send(formatted, recipient=recipient)
        
    async def ask_confirmation(
        self,
        question: str,
        recipient: str,
        callback_data_prefix: str = "confirm"
    ) -> bool:
        """Ask for confirmation with Yes/No buttons."""
        keyboard = {
            "inline_keyboard": [[
                {"text": "✅ Yes", "callback_data": f"{callback_data_prefix}:yes"},
                {"text": "❌ No", "callback_data": f"{callback_data_prefix}:no"}
            ]]
        }
        return await self.send(
            f"❓ *Confirmation Required*\n\n{question}",
            recipient=recipient,
            keyboard=keyboard
        )
        
    async def send_action_result(self, action: str, target: str, success: bool, details: str = ""):
        """Send notification about an action result"""
        status = "✅ Success" if success else "❌ Failed"
        message = (
            f"🤖 *Brain Action*\n\n"
            f"*Action:* `{action}`\n"
            f"*Target:* `{target}`\n"
            f"*Status:* {status}\n"
        )
        if details: message += f"\n*Details:* {details}"
        await self.send(message)
    
    async def initiate_proactive_chat(self, goals: list = None, mood: str = "OPTIMISTIC", energy: float = 1.0):
        """
        Brain 3.0: Proactively initiate a conversation with the Boss.
        """
        from core.identity import AgentIdentity
        from core.brain.model import SharedModelProvider
        
        identity = AgentIdentity()
        identity.current_mood = mood
        identity.energy = energy
        
        prompt = identity.get_system_prompt("proactive")
        
        # Add goals context if available
        if goals:
            goals_text = "\n".join([f"- {g.get('title')}: {g.get('motivation')}" for g in goals[:3]])
            prompt += f"\n\nCURRENT GOALS:\n{goals_text}"
            
        try:
            model = SharedModelProvider.get_model()
            response = await model.ainvoke(prompt)
            
            # Fix: Handle AIMessage object
            content = response.content if hasattr(response, 'content') else str(response)
            message = content.strip()
            
            if message:
                logger.info(f"[TELEGRAM] Initiating proactive chat: {message[:50]}...")
                await self.send(message)
                return True
        except Exception as e:
            logger.error(f"[TELEGRAM] Failed to initiate proactive chat: {e}")
            
        return False
    
    async def send_report_actions(self, report_id: str, report_text: str, recipient: str) -> bool:
        """Send a report with action buttons."""
        keyboard = {
            "inline_keyboard": [[
                {"text": "⬜ NONE", "callback_data": f"report:{report_id}:NONE"},
                {"text": "⚠️ WARN", "callback_data": f"report:{report_id}:WARN"},
            ], [
                {"text": "🗑️ REMOVE", "callback_data": f"report:{report_id}:REMOVE"},
                {"text": "❌ DISMISS", "callback_data": f"report:{report_id}:DISMISS"}
            ]]
        }
        return await self.send(report_text, recipient=recipient, keyboard=keyboard)
        
    async def _api_call(self, method: str, params: dict = None) -> dict:
        """Make a Telegram Bot API call"""
        if not self._session: return {"ok": False, "error": "Not connected"}
        url = f"{self.api_url}/{method}"
        try:
            async with self._session.post(url, json=params or {}) as response:
                return await response.json()
        except Exception as e:
            return {"ok": False, "error": str(e)}
            
    async def _set_commands(self):
        """Set the bot commands menu"""
        commands = [{"command": cmd, "description": desc} for cmd, desc in self.COMMANDS.items()]
        result = await self._api_call("setMyCommands", {"commands": commands, "scope": {"type": "default"}})
        if result.get("ok"):
            logger.info(f"[TELEGRAM] Successfully registered {len(commands)} commands")
        else:
            logger.error(f"[TELEGRAM] Failed to register commands: {result}")
        
    def _parse_message(self, msg: dict) -> Message:
        """Parse a Telegram message into our Message format"""
        text = msg.get("text", "")
        sender = msg.get("from", {})
        msg_type = MessageType.COMMAND if text.startswith("/") else MessageType.TEXT
        return Message(
            id=str(msg.get("message_id")),
            channel=self.name,
            type=msg_type,
            content=text,
            sender_id=str(sender.get("id")),
            sender_name=sender.get("first_name", "Unknown"),
            chat_id=str(msg.get("chat", {}).get("id")),
            metadata={
                "username": sender.get("username"),
                "is_bot": sender.get("is_bot", False),
                "chat_type": msg.get("chat", {}).get("type"),
                "thread_id": msg.get("message_thread_id")
            }
        )
        
    def _parse_callback(self, callback: dict) -> Message:
        """Parse a callback query into our Message format"""
        sender = callback.get("from", {})
        msg = callback.get("message", {})
        return Message(
            id=callback.get("id"),
            channel=self.name,
            type=MessageType.CALLBACK,
            content=callback.get("data", ""),
            sender_id=str(sender.get("id")),
            sender_name=sender.get("first_name", "Unknown"),
            chat_id=str(msg.get("chat", {}).get("id")),
            reply_to=str(msg.get("message_id")),
            metadata={
                "callback_id": callback.get("id"),
                "original_message": msg
            }
        )
