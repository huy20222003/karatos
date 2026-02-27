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
from channels.base import Channel, Message, MessageType

logger = get_logger()

# Singleton instance - keeping for compatibility but preferring ChannelManager
from channels.base import get_channel_manager

def get_telegram_channel() -> Optional["TelegramChannel"]:
    """Get the active Telegram channel instance"""
    from channels.base import get_channel
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
                "timeout": settings.telegram_polling_timeout,
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

        # Smart underscore escaping: Already handled inside normalize_markdown for V1 consistency
        safe_text = text_to_send

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
        parse_mode: str = "Markdown",
        **kwargs
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
            
            if "keyboard" in kwargs:
                data.add_field('reply_markup', json.dumps(kwargs["keyboard"]))

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
            return f"PROTECTEDCODEBLOCK{len(code_blocks)-1}PTC"
        
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

        # 5. SMART ESCAPING: Escape bare underscores while code blocks are PROTECTED
        if "_" in text:
            text = self._escape_underscores(text)
        
        # 6. Restore code blocks
        for i, block in enumerate(code_blocks):
            text = text.replace(f"PROTECTEDCODEBLOCK{i}PTC", block)
        
        return text

    def escape_markdown(self, text: str) -> str:
        """Escape ALL special characters for Telegram Markdown (V1) — used as last resort fallback."""
        if not text: return ""
        return text.replace("_", "\\_").replace("*", "\\*").replace("`", "\\`").replace("[", "\\[")

    def _escape_underscores(self, text: str) -> str:
        """Escape underscores that are NOT part of identifiers, filenames or paths.
        In V1, bare underscores are very risky. High-risk strings are wrapped in code backticks."""
        if not text: return ""
        import re as _re
        
        # 1. Protect @usernames separately (they shouldn't be backticked by default)
        usernames = []
        def save_username(match):
            usernames.append(match.group(0))
            return f"PTCUSERNAME{len(usernames)-1}PTC"
        text = _re.sub(r'@[a-zA-Z0-9_]+', save_username, text)
        
        # 2. Identify and protect high-risk strings (filenames, paths, identifiers)
        # These contain underscores and are surrounded by path/word characters.
        # Support for Unicode (Vietnamese), dots, slashes, backslashes, colons.
        protected_blocks = []
        def save_protected(match):
            protected_blocks.append(f"`{match.group(0)}`")
            return f"PTCPROT{len(protected_blocks)-1}PTC"
        
        allowed = r'[a-zA-Z0-9\u00C0-\u1EF9\._\\/:-]'
        path_regex = f'{allowed}*_{allowed}*'
        text = _re.sub(path_regex, save_protected, text)
        
        # 3. Escape REMAINING bare underscores
        text = text.replace("_", "\\_")
        
        # 4. Restore protected blocks
        for i, val in enumerate(protected_blocks):
            text = text.replace(f"PTCPROT{i}PTC", val)
            
        # 5. Restore usernames and escape them if not already in code (unlikely given order)
        for i, uname in enumerate(usernames):
            placeholder = f"PTCUSERNAME{i}PTC"
            if placeholder in text:
                escaped_uname = uname.replace("_", "\\_")
                text = text.replace(placeholder, escaped_uname)
                
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
        
    async def _api_call(self, method: str, params: dict = None, retries: int = 3) -> dict:
        """
        Make a Telegram Bot API call with robust retry logic.
        Handles:
        - Network timeouts & connection errors
        - Rate limits (429)
        - Transient server errors (5xx)
        """
        if not self._session or self._session.closed:
            logger.warning("[TELEGRAM] ClientSession is closed or missing. Attempting to reconnect...")
            if not await self.connect():
                return {"ok": False, "error": "Not connected"}

        url = f"{self.api_url}/{method}"
        attempt = 0
        backoff = 1.0 # Start with 1s backoff

        while attempt < retries:
            attempt += 1
            try:
                # Use polling timeout + extra buffer for the request itself
                request_timeout = settings.telegram_polling_timeout + 15
                async with self._session.post(url, json=params or {}, timeout=request_timeout) as response:
                    # Case 1: Success
                    if response.status == 200:
                        return await response.json()
                    
                    # Case 2: Rate Limited (429)
                    elif response.status == 429:
                        data = await response.json()
                        retry_after = data.get("parameters", {}).get("retry_after", backoff)
                        logger.warning(f"[TELEGRAM] Rate limited (429). Retrying after {retry_after}s (Attempt {attempt}/{retries})")
                        await asyncio.sleep(retry_after)
                        continue
                        
                    # Case 3: Transient Server Error (5xx)
                    elif response.status >= 500:
                        logger.warning(f"[TELEGRAM] Server Error {response.status}. Retrying in {backoff}s... (Attempt {attempt}/{retries})")
                        await asyncio.sleep(backoff)
                        backoff *= 2
                        continue
                    
                    # Case 4: Other request errors (4xx) - usually not retryable
                    else:
                        result = await response.json()
                        logger.error(f"[TELEGRAM] API Error {response.status}: {result}")
                        return result

            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                # This catches the 'semaphore timeout', connection refused, dns issues, etc.
                err_str = str(e) or repr(e)
                logger.warning(f"[TELEGRAM] Network error on {method}: {err_str}. Retrying in {backoff}s... (Attempt {attempt}/{retries})")
                
                # If it's a semaphore/underlying connection issue, recreating the session MIGHT help
                if "semaphore" in err_str.lower() or "closed" in err_str.lower():
                    logger.info("[TELEGRAM] Critical connection error detected. Recreating session tracker.")
                    await self.disconnect()
                    await self.connect()

                if attempt == retries:
                    logger.error(f"[TELEGRAM] Max retries reached for {method}. Final error: {err_str}")
                    # For long-polling getUpdates, a stuck connection can feel like a "lost" bot.
                    # As a safety net, force a lightweight reconnect so the next loop starts clean.
                    if method == "getUpdates":
                        try:
                            logger.info("[TELEGRAM] Forcing reconnect after repeated getUpdates timeouts...")
                            await self.disconnect()
                            await self.connect()
                        except Exception as reconnect_err:
                            logger.debug(f"[TELEGRAM] Reconnect after getUpdates failure also failed: {reconnect_err}")
                    return {"ok": False, "error": err_str}
                
                await asyncio.sleep(backoff)
                backoff *= 2
        
        return {"ok": False, "error": "Max retries exceeded"}
            
    async def _set_commands(self):
        """Set the bot commands menu"""
        commands = [{"command": cmd, "description": desc} for cmd, desc in self.COMMANDS.items()]
        result = await self._api_call("setMyCommands", {"commands": commands, "scope": {"type": "default"}})
        if result.get("ok"):
            logger.info(f"[TELEGRAM] Successfully registered {len(commands)} commands")
        else:
            logger.error(f"[TELEGRAM] Failed to register commands: {result}")
        
    async def _download_file(self, file_id: str, file_name: str) -> Optional[str]:
        """Download a file from Telegram into a temporary directory.
        Returns local temp path or None. File is auto-cleaned by OS."""
        try:
            import tempfile
            # 1. Get file path from Telegram
            result = await self._api_call("getFile", {"file_id": file_id})
            if not result.get("ok"):
                logger.error(f"[TELEGRAM] getFile failed: {result}")
                return None
            
            tg_file_path = result["result"]["file_path"]
            download_url = f"https://api.telegram.org/file/bot{self.token}/{tg_file_path}"
            
            # 2. Download to temporary directory (auto-cleaned by OS)
            # Using suffix to preserve file extension for type detection
            import os
            _, ext = os.path.splitext(file_name)
            tmp_fd, local_path = tempfile.mkstemp(suffix=ext, prefix="niva_tmp_")
            
            async with self._session.get(download_url) as resp:
                if resp.status == 200:
                    with os.fdopen(tmp_fd, "wb") as f:
                        f.write(await resp.read())
                    logger.info(f"[TELEGRAM] File saved to temp: {local_path} (auto-cleanup)")
                    return local_path
                else:
                    os.close(tmp_fd)
                    os.unlink(local_path)
                    logger.error(f"[TELEGRAM] File download HTTP {resp.status}")
                    return None
        except Exception as e:
            logger.error(f"[TELEGRAM] File download error: {e}")
            return None

    async def get_file_bytes(self, file_id: str) -> Optional[bytes]:
        """Fetch file bytes directly from Telegram API (In-memory)."""
        try:
            # 1. Get file path
            result = await self._api_call("getFile", {"file_id": file_id})
            if not result.get("ok"):
                return None
            
            tg_file_path = result["result"]["file_path"]
            download_url = f"https://api.telegram.org/file/bot{self.token}/{tg_file_path}"
            
            # 2. Stream to memory
            async with self._session.get(download_url) as resp:
                if resp.status == 200:
                    return await resp.read()
        except Exception as e:
            logger.error(f"[TELEGRAM] get_file_bytes error: {e}")
        return None

    async def answer_callback_query(self, callback_query_id: str, text: Optional[str] = None, show_alert: bool = False):
        """
        Acknowledge a callback query to stop the loading state on the button.
        Required by Telegram Bot API to provide immediate visual feedback.
        """
        params = {"callback_query_id": callback_query_id}
        if text:
            params["text"] = text
            params["show_alert"] = show_alert
            
        logger.debug(f"[TELEGRAM] Answering callback {callback_query_id}")
        return await self._api_call("answerCallbackQuery", params)

    def _parse_message(self, msg: dict) -> Message:
        """Parse a Telegram message into our Message format.
        Handles text, captions, and document/photo/audio uploads."""
        # Priority: text > caption (for file messages)
        text = msg.get("text") or msg.get("caption") or ""
        sender = msg.get("from", {})
        msg_type = MessageType.COMMAND if text.startswith("/") else MessageType.TEXT
        
        metadata = {
            "username": sender.get("username"),
            "is_bot": sender.get("is_bot", False),
            "chat_type": msg.get("chat", {}).get("type"),
            "thread_id": msg.get("message_thread_id")
        }
        
        # Detect document uploads (DOCX, PDF, etc.)
        doc = msg.get("document")
        if doc:
            metadata["document"] = {
                "file_id": doc.get("file_id"),
                "file_name": doc.get("file_name", "unknown_file"),
                "mime_type": doc.get("mime_type", ""),
                "file_size": doc.get("file_size", 0),
            }
            # If no caption, synthesize a description so the router sees something
            if not text:
                text = f"[User sent a file: {doc.get('file_name', 'unknown')}]"
        # Detect photo uploads
        photos = msg.get("photo")
        if photos:
            # Telegram sends multiple sizes, pick the largest
            best_photo = photos[-1] if photos else None
            if best_photo:
                metadata["photo"] = {
                    "file_id": best_photo.get("file_id"),
                    "width": best_photo.get("width"),
                    "height": best_photo.get("height"),
                }
                if not text:
                    text = "[User sent a photo]"
        
        # Detect voice messages
        voice = msg.get("voice")
        if voice:
            metadata["voice"] = {
                "file_id": voice.get("file_id"),
                "mime_type": voice.get("mime_type", ""),
                "file_size": voice.get("file_size", 0),
                "duration": voice.get("duration", 0)
            }
            if not text:
                text = "[User sent a voice message]"
                
        # Detect audio files
        audio = msg.get("audio")
        if audio:
            metadata["audio"] = {
                "file_id": audio.get("file_id"),
                "file_name": audio.get("file_name", "unknown_audio"),
                "mime_type": audio.get("mime_type", ""),
                "file_size": audio.get("file_size", 0),
                "duration": audio.get("duration", 0)
            }
            if not text:
                text = f"[User sent an audio file: {audio.get('file_name', 'audio')}]"
        
        return Message(
            id=str(msg.get("message_id")),
            channel=self.name,
            type=msg_type,
            content=text,
            sender_id=str(sender.get("id")),
            sender_name=sender.get("first_name", "Unknown"),
            chat_id=str(msg.get("chat", {}).get("id")),
            metadata=metadata
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
