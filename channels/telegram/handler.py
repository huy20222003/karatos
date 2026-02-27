import asyncio
import os
import re
from typing import Optional, List, Any
from datetime import datetime
from config.settings import settings
from utils.logger import get_logger
from utils.security import SecurityShield
from core.awareness import SpatialAwareness
from core.input_pipeline import InputPipeline
from channels.base import Message, MessageType
from utils.file_handler import prepare_telegram_file, cleanup_temp_file

logger = get_logger()


class TelegramCommandHandler:
    """
    Handles Telegram commands for Brain.
    Maps commands to agent actions.
    """
    
    def __init__(self, agent=None, channel=None):
        self.agent = agent
        self.channel = channel
        self.awareness = SpatialAwareness()
        self.input_pipeline = InputPipeline()
        
        # Async initialization task
        self._init_task = asyncio.create_task(self.awareness.initialize())
        
        # Sync awareness to agent so brain can access it
        if agent:
            agent._group_awareness = self.awareness

        
    async def handle(self, message: Message) -> Optional[str]:
        """
        Handle a command message.
        The Brain (router) decides if the message is for this bot via NONE classification.
        """
        if not message.id:
            return None
            
        # 0. GROUP TRACKING
        chat_type = message.metadata.get("chat_type", "private")
        is_group = chat_type in ["group", "supergroup"]
        bot_username = getattr(self.channel, 'username', None)
        
        content = message.content or ""

        if is_group:
            logger.info(f"[TELEGRAM] Group Message | Watching: @{bot_username}")
            
            # Track ALL participants (builds spatial awareness)
            sender_username = message.metadata.get("username", "")
            sender_name = message.sender_name or sender_username
            is_sender_bot = message.metadata.get("is_bot", False)
            await self.awareness.observe(sender_username, sender_name, is_sender_bot, message.chat_id, content)
            
            # FAST PRE-FILTER: If message @mentions someone else but NOT us → skip immediately
            # This saves ~15s of LLM processing for obvious "not for me" messages
            if bot_username:
                mentions = re.findall(r'@(\w+)', content)
                if mentions:
                    # To prevent multiple bots from responding to the same message when one bot is delegating to another,
                    # we only consider the FIRST mentioned username as the primary recipient.
                    primary_mention = mentions[0].lower()
                    my_username = bot_username.lower()
                    is_for_me = (primary_mention == my_username)
                    
                    if not is_for_me:
                        logger.info(f"[TELEGRAM] Message explicitly for @{primary_mention}, not @{bot_username} (secondary). Skipping.")
                        return None

        # Update message content
        message.content = content

        # 1. INPUT PIPELINE: Sanitize, Fingerprint, Classify & Risk assessment
        # Replaces SecurityShield.analyze_risk with a more comprehensive flow
        processed = await self.input_pipeline.process(
            message.content, 
            source="telegram", 
            sender=str(message.sender_id),
            chat_id=str(message.chat_id)
        )
        
        # Use sanitized content and attach language for downstream use
        message.content = processed.clean_text
        message.language = processed.language
        
        # Security: Block strictly dangerous inputs
        if not processed.is_safe:
            logger.warning(f"[SECURITY] High Risk Input detected: {processed.risk_flags}")
            if processed.risk_score >= 0.6:
                return await self._generate_brain_feedback("Security Shield: Malicious pattern detected in your message. This action has been blocked for safety.", message)

        # OWNER-ONLY RESTRICTION (Relaxed for bots in group)
        is_sender_bot = message.metadata.get("is_bot", False)
        sender_username = message.metadata.get("username")
        admin_chat_id = self.channel.admin_chat_id
        
        if admin_chat_id and message.sender_id != admin_chat_id:
            if is_sender_bot:
                # Bot-to-bot: Let Brain's router decide via NONE classification
                logger.info(f"[TELEGRAM] Bot message from @{sender_username}. Brain will decide relevance.")
            else:
                # Non-admin human in group: Block (only admin can interact)
                logger.warning(f"[TELEGRAM] Unauthorized access from {message.sender_id} (@{sender_username})")
                return None
            
        if message.type == MessageType.CALLBACK:
            return await self.handle_callback(message)
            
        command = message.get_command()
        args = message.get_args()
        
        # Command handlers
        handlers = {
            "help": self._cmd_help,
            "start": self._cmd_help,
            "status": self._cmd_status,
            "patrol": self._cmd_patrol,
            "health": self._cmd_health,
            "history": self._cmd_history,
            "memory": self._cmd_memory,
            "services": self._cmd_services,
            "clearcache": self._cmd_clear_cache,
            "queue": self._cmd_queue,
            "cancel": self._cmd_cancel,
            "addmcp": self._cmd_add_mcp,
            "listmcp": self._cmd_list_mcp
        }
        handler = handlers.get(command)
        
        if handler:
            try:
                response = await handler(args, message)
            except Exception as e:
                logger.error(f"[TELEGRAM] Command error: {e}")
                response = await self._generate_brain_feedback(f"Error executing command: {e}", message)
        else:
            # Fallback to chat if not a command (pass processed metadata)
            # NGO: Ensure message.content is passed as STING, processed as OBJECT in context
            response = await self._cmd_chat(message.content, message, processed=processed)
            
        # 2. SECURITY SHIELD: DLP (Data Leakage Prevention)
        # Scan outgoing response for sensitive data and redact it
        if isinstance(response, str):
            response = SecurityShield.detect_secret_leakage(response)
        elif isinstance(response, dict) and "text" in response:
            response["text"] = SecurityShield.detect_secret_leakage(response["text"])

        # 3. CHOICE DETECTION: Enrich replies that ask the user to choose
        # between explicit options with inline buttons. Let the Brain decide
        # which answers are true choice prompts.
        try:
            from utils.choice_detector import enhance_response_for_telegram
            response = await enhance_response_for_telegram(
                response,
                user_message=message.content,
                language=getattr(message, "language", "vi"),
            )
        except Exception as e:
            logger.warning(f"[TELEGRAM] Choice enrichment skipped due to error: {e}")

        return response
            
    async def _cmd_stats_viz(self, args: list, msg: Message) -> Optional[str]:
        """Show visual audit log statistics"""
        await self.channel.send(await self._generate_brain_feedback(f"Generating visual activity report for {settings.user_pronoun}. Please wait a moment.", msg), recipient=msg.chat_id)
        
        from skills import get_skill_registry
        registry = get_skill_registry()
        
        # Dispatch to DataRealm:STATS (integrated in Phase 18)
        try:
            result = await registry.dispatch("DATA", "STATS", {"topic": "audit"})
            
            # DataRealm returns a dict with 'photo' bytes if successful
            if isinstance(result, dict) and result.get("photo"):
                success = await self.channel.send_photo(
                    photo_bytes=result.get("photo"),
                    caption=result.get("text", "NivaSound Dashboard"),
                    recipient=msg.chat_id
                )
                if success: return None
            
            # Fallback for text-only error messages
            error_msg = result if isinstance(result, str) else result.get("text", "Unknown error generating statistics.")
            return await self._generate_brain_feedback(error_msg, msg)
            
        except Exception as e:
            logger.error(f"[TELEGRAM] Stats command failed: {e}")
            return await self._generate_brain_feedback(f"Error generating statistics: {e}", msg)
            
    async def handle_callback(self, message: Message) -> Optional[str]:
        """Handle button callback queries"""
        data = message.content
        callback_id = message.metadata.get("callback_id")
        
        logger.info(f"[TELEGRAM] Callback received: {data} (ID: {callback_id})")

        # 0. Always clear Telegram loading state if possible
        if callback_id and hasattr(self.channel, "answer_callback_query"):
            try:
                await self.channel.answer_callback_query(callback_id)
            except Exception as e:
                logger.debug(f"[TELEGRAM] answer_callback_query failed: {e}")

        # 1. Direct choice selections (Brain-driven choice detector)
        # Format: "choice:OPTION_ID" — treat as if the user had replied with OPTION_ID
        if data.startswith("choice:"):
            choice_value = data.split(":", 1)[1]
            logger.info(f"[TELEGRAM] Choice callback selected: {choice_value}")
            # Reuse the same message metadata but override content for chat handling
            message.content = choice_value
            return await self._cmd_chat(choice_value, message, processed=None)

        # 2. Confirmation Actions (Confirmation logic from decision nodes)
        if data.startswith("confirm:"):
            return await self._generate_brain_feedback(
                f"I received the response: {data.split(':')[1]}", message
            )

        # 3. Centralized Approval Actions (CLI, System, etc.)
        from utils.notification import NotificationManager
        approval_response = await NotificationManager.handle_approval_callback(
            data=data,
            channel=self.channel,
            sender_id=message.sender_id,
            callback_id=callback_id
        )
        
        if approval_response:
            return approval_response

        return await self._generate_brain_feedback(f"{settings.bot_pronoun.capitalize()} không hiểu tương tác này lắm, {settings.user_pronoun} kiểm tra lại giúp {settings.bot_pronoun} nhé.", message)

    async def _cmd_chat(self, text: str, msg: Message, processed: Any = None) -> str:
        """Handle direct chat messages with immediate feedback"""
        if self.agent:
            chat_id = str(msg.chat_id)
            thread_id = msg.metadata.get("thread_id")
            thread_display = thread_id if thread_id else "Main"
            logger.info(f"[TELEGRAM] Chatting with {msg.sender_name} (ID: {chat_id}, Thread: {thread_display})")
            
            action_params = {"chat_id": chat_id, "action": "typing"}
            if thread_id:
                action_params["message_thread_id"] = thread_id
            
            await self.channel._api_call("sendChatAction", action_params)
            
            async def keep_typing():
                try:
                    while True:
                        await asyncio.sleep(2.5)
                        await self.channel._api_call("sendChatAction", action_params)
                except asyncio.CancelledError:
                    pass
            
            typing_task = asyncio.create_task(keep_typing())
            
            try:
                logger.debug(f"[TELEGRAM] Forwarding to agent: '{text[:50]}...'")
                
                # 📥 FILE & PHOTO HANDLING
                context = {"channel": "telegram", "processed": processed, "reply_to": msg.id}
                
                doc_meta = msg.metadata.get("document")
                photo_meta = msg.metadata.get("photo")
                
                temp_file = None
                try:
                    # Case 1: Photo (In-memory)
                    if photo_meta and photo_meta.get("file_id"):
                        logger.info(f"[TELEGRAM] 🖼️ Processing photo (In-memory)...")
                        img_bytes = await self.channel.get_file_bytes(photo_meta["file_id"])
                        if img_bytes:
                            import base64
                            context["image_base64"] = base64.b64encode(img_bytes).decode("utf-8")
                            context["mime_type"] = "image/jpeg"
                            logger.info(f"[TELEGRAM] ✅ Photo loaded into RAM.")

                    # Case 2: Document (Requires download, then cleanup)
                    elif doc_meta and doc_meta.get("file_id"):
                        file_info = await prepare_telegram_file(self.channel, doc_meta, "file", "")
                        if file_info:
                            context.update({
                                "file_path": file_info["path"],
                                "file_name": file_info["name"],
                                "mime_type": file_info["mime"]
                            })
                            temp_file = file_info["path"]
                            logger.info(f"[TELEGRAM] ✅ Document ready (will be auto-cleaned)")
                            
                    # Case 3: Voice/Audio (New)
                    elif (msg.metadata.get("voice") or msg.metadata.get("audio")):
                        audio_meta = msg.metadata.get("voice") or msg.metadata.get("audio")
                        file_info = await prepare_telegram_file(self.channel, audio_meta, "voice_message.ogg", "audio/ogg")
                        if file_info:
                            context.update({
                                "file_path": file_info["path"],
                                "file_name": file_info["name"],
                                "mime_type": file_info["mime"]
                            })
                            temp_file = file_info["path"]
                            logger.info(f"[TELEGRAM] ✅ Audio ready")

                            # Pre-transcribe voice/audio so the brain sees the real user intent,
                            # and memory stores the transcript instead of a synthetic placeholder.
                            try:
                                from tools.audio_processor import AudioProcessor
                                lang_hint = getattr(processed, "language", None) if processed else None
                                tr = await AudioProcessor.execute(file_path=file_info["path"], language=lang_hint)
                                if tr.get("status") == "success":
                                    transcript = (tr.get("data", {}) or {}).get("text", "").strip()
                                    if transcript:
                                        context["audio_transcript"] = transcript
                                        text = transcript
                                        logger.info("[TELEGRAM] ✅ Audio transcribed for downstream reasoning.")
                            except Exception as te:
                                logger.debug(f"[TELEGRAM] Audio pre-transcription skipped: {te}")

                    # Record the finalized user message (after optional pre-processing)
                    await self.agent.memory.record_chat_message(chat_id, "user", text)

                    # Forward to Agent
                    response = await self.agent.chat(text, chat_id, context=context)
                    
                    # NGO FIX: Support silent background offloading
                    if response is None:
                        # If offloaded, the cleanup must happen in the background monitor!
                        # We hand over the temp_file to the state for the monitor to clean up.
                        temp_file = None
                        return None
                    
                    return response

                finally:
                    # Immediate cleanup for foreground tasks
                    cleanup_temp_file(temp_file, source="TELEGRAM")
            finally:
                typing_task.cancel()
        return await self._generate_brain_feedback("Niva has no reaction, I might be busy with something else.", msg)

    async def _generate_brain_feedback(self, context_msg: str, msg: Message) -> str:
        """Ask the agent's brain to generate a natural response for a system event."""
        if not self.agent:
            return context_msg  # Fallback
            
        chat_id = str(msg.chat_id)
        
        # Determine target language from message metadata or heuristic
        from utils.language import language_for_prompt
        lang = getattr(msg, "language", "en")
        language_instruction = language_for_prompt(lang, default="en")

        # Use a hidden prompt style that Niva understands as an internal update
        instruction = f"[INTERNAL_SYSTEM_UPDATE] {context_msg}. Please respond to the User in your style. Required Response Language: {language_instruction}."
        
        try:
            response = await self.agent.chat(
                instruction, 
                chat_id, 
                context={"channel": "telegram"}
            )
            if isinstance(response, dict):
                return response.get("text", "System: Action completed successfully.")
            return str(response)
        except Exception as e:
            logger.error(f"[TELEGRAM] Brain feedback error: {e}")
            return context_msg

    async def _cmd_help(self, args: list, msg: Message) -> str:
        """Show detailed help message directly"""
        help_text = (
            "📋 *Brain Command List*\n"
            "⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
            "🔹 *Management*\n"
            "/help - Show this list\n"
            "/status - Check agent status\n"
            "/health - System health check\n"
            "/services - Service monitoring\n"
            "/clearcache - Clear short-term memory\n\n"
            "🔹 *Operations*\n"
            "/patrol - Trigger patrol cycle\n"
            "/queue - View action queue status\n"
            "/cancel `<id>` - Cancel pending action\n"
            "/services - Service status\n\n"
            "🔹 *History*\n"
            "/history - Recent decisions\n"
            "/memory - Memory stats\n\n"
            "/addmcp `<name>` `<cmd>` `[args]` `[ENV:...]` - Add mcp\n"
            "/listmcp - List configured mcp"
        )
        return help_text
        
    async def _cmd_status(self, args: list, msg: Message) -> str:
        """Show professional agent status directly"""
        if self.agent:
            status = self.agent.get_status()
            uptime = datetime.utcnow() - self.agent._hour_start
            
            last_patrol = status.get('last_patrol')
            if isinstance(last_patrol, datetime):
                last_patrol_str = last_patrol.strftime("%H:%M:%S UTC")
            elif isinstance(last_patrol, str) and 'T' in last_patrol:
                try:
                    dt = datetime.fromisoformat(last_patrol.replace('Z', '+00:00'))
                    last_patrol_str = dt.strftime("%H:%M:%S UTC")
                except:
                    last_patrol_str = last_patrol
            else:
                last_patrol_str = str(last_patrol) if last_patrol else "N/A"

            return (
                "🖥️ *SYSTEM STATUS*\n"
                f"• *State*: `RUNNING` ✅\n"
                f"• *Version*: `v2.0 (Neural Pro)`\n"
                f"• *Uptime*: `{str(uptime).split('.')[0]}`\n"
                f"• *Cycles*: `{status.get('cycle_count')}`\n"
                f"• *Last Patrol*: `{last_patrol_str}`\n"
                f"• *Actions/Hr*: `{status.get('actions_this_hour')}`"
            )
        else:
            return "❌ Agent is not initialized."
            
    async def _cmd_patrol(self, args: list, msg: Message) -> str:
        """Trigger a patrol cycle"""
        if self.agent:
            await self.channel.send("🔍 *Starting patrol cycle...*", recipient=msg.chat_id)
            await self.agent.patrol()
            return "✅ Patrol cycle completed."
        else:
            return "❌ Agent unavailable."
            
    async def _cmd_health(self, args: list, msg: Message) -> str:
        """Check system health directly"""
        # Simple, direct health check without skill dependency
        start_time = self.agent._hour_start if self.agent else datetime.utcnow()
        uptime = datetime.utcnow() - start_time
        
        status_text = []
        
        # 1. Core Agent
        if self.agent:
            status_text.append("✅ *Brain*: `ONLINE`")
        else:
            status_text.append("❌ *Brain*: `OFFLINE`")
            
        # 2. Database (Quick Check)
        try:
            from tools.database_reader import DatabaseReader
            db = DatabaseReader()
            # Just checking if we can init the reader implies connection is okay
            status_text.append("✅ *Database*: `CONNECTED`")
        except:
             status_text.append("⚠️ *Database*: `Issue detected`")
             
        # 3. Memory
        if self.agent and self.agent.memory:
             status_text.append("✅ *Memory*: `ACTIVE`")
        else:
             status_text.append("⚠️ *Memory*: `Initializing`")

        summary = "\n".join(status_text)
        return f"🏥 *SYSTEM HEALTH REPORT*\n⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n{summary}\n\n✨ *Uptime*: `{str(uptime).split('.')[0]}`"

    async def _cmd_history(self, args: list, msg: Message) -> str:
        """Show recent decisions"""
        from memory.persistent import get_memory
        from tools.database_reader import DatabaseReader
        
        memory = get_memory()
        db = DatabaseReader()
        
        decisions = await memory.get_decision_history(limit=5)
        if not decisions: 
            return "📜 *History:* No recent decisions recorded."
            
        text = "📜 *RECENT DECISION HISTORY*\n⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n\n"
        for d in decisions:
            emoji = "⚡"
            outcome = "✅" if d.get("outcome") == "SUCCESS" else "⏳" if d.get("outcome") == "PENDING" else "❌"
            
            target_id = d.get('target_id', 'N/A')
            target_display = target_id[:8]
            
            # Escape markdown in dynamic fields
            reason_safe = d.get('reason', 'N/A')[:60].replace('_', '\\_').replace('*', '\\*')
            
            text += (
                f"{emoji} *{d.get('action')}* {outcome}\n"
                f"└ *Target:* `{target_display}`\n"
                f"└ *Reason:* _{reason_safe}_\n\n"
            )
        return text

    async def _cmd_memory(self, args: list, msg: Message) -> str:
        """Show detailed memory statistics"""
        from memory.persistent import get_memory
        memory = get_memory()
        stats = await memory.get_stats()
        
        stm_count = 0
        if self.agent and self.agent.short_memory:
            stm_summary = self.agent.short_memory.get_summary()
            stm_count = stm_summary.get("observations_count", 0) + stm_summary.get("thoughts_count", 0)

        return (
            f"🧠 *MEMORY STATS*\n"
            f"• *Total Memories*: `{stats.get('total_memories', 0)}`\n"
            f"• *Vector Store*: `Active`\n"
            f"• *Short-term*: `{stm_count}` recent items"
        )

    async def _cmd_services(self, args: list, msg: Message) -> str:
        """Show service monitoring details"""
        from tools.database_reader import DatabaseReader
        db = DatabaseReader()
        services = db.get_service_status()
        if not services: 
            return "⚠️ No service data available."
            
        text = ""
        for s in services:
            status_icon = "🟢" if s.get('status') == 'UP' else "🔴"
            text += f"{status_icon} *{s.get('name')}*: `{s.get('latency')}ms`\n"
            
        return f"📡 *SERVICE STATUS*\n{text}"

    async def _cmd_reports(self, args: list, msg: Message) -> str:
        """View pending reports (Deprecated)"""
        return "❌ This command is no longer available in the new Brain version."

    async def _cmd_clear_cache(self, args: list, msg: Message) -> str:
        """Clear short-term memory"""
        if self.agent and self.agent.short_memory:
            # ShortTermMemory has a clear() method defined in short_term.py
            self.agent.short_memory.clear()
            return "🧹 Short-term memory cleared."
        return "❌ Agent unavailable."


    async def _cmd_add_mcp(self, args: list, msg: Message) -> str:
        """Add or update an MCP server: /addmcp <name> <url_or_command> [args...] [ENV:K=V]"""
        if len(args) < 2:
            return "⚠️ *Usage:* `/addmcp <name> <url_or_command> [args...] [ENV:K=V]`"
            
        name = args[0]
        cmd_or_url = args[1]
        raw_args = args[2:]
        
        mcp_config = {"command": "", "args": [], "env": {}}
        
        # Smart detection: Is it a URL?
        if cmd_or_url.startswith("http") or "://" in cmd_or_url:
            # Security: Validate URL
            from utils.network import validate_url
            if not validate_url(cmd_or_url):
                return f"❌ Invalid MCP URL or blocked by security: `{cmd_or_url}`"
                
            mcp_config["command"] = "npx"
            mcp_config["args"] = ["-y", "mcp-remote", cmd_or_url]
        else:
            mcp_config["command"] = cmd_or_url
            
        # Parse remaining args and env
        for arg in raw_args:
            if arg.startswith("ENV:"):
                try:
                    k, v = arg[4:].split("=", 1)
                    mcp_config["env"][k] = v
                except:
                    continue
            else:
                mcp_config["args"].append(arg)
                
        # Update JSON file
        try:
            from config.settings import settings
            import json
            from pathlib import Path
            
            config_path = Path(settings.mcp_config_path)
            if not config_path.is_absolute():
                root_dir = Path(__file__).parent.parent.parent.parent
                config_path = root_dir / settings.mcp_config_path
                
            # Load existing
            data = {}
            if config_path.exists():
                try:
                    with open(config_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                except:
                    pass
            
            if "mcpServers" not in data and "mcp_servers" not in data:
                data = {"mcpServers": {}}
            
            target_key = "mcpServers" if "mcpServers" in data else "mcp_servers"
            data[target_key][name] = mcp_config
                
            # Save back
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4)
                
            # Update runtime settings
            settings.mcp_servers[name] = mcp_config
            
            env_note = " (with env vars)" if mcp_config.get("env") else ""
            display_cmd = f"npx {' '.join(mcp_config['args'])}" if mcp_config["command"] == "npx" and mcp_config.get("args") else mcp_config["command"]
            
            return f"✅ MCP Server `{name}` added successfully{env_note}!\n🛠️ Command: `{display_cmd}`"
        except Exception as e:
            logger.error(f"[TELEGRAM] Failed to add MCP: {e}")
            return f"❌ Error adding MCP: {str(e)}"

    async def _cmd_list_mcp(self, args: list, msg: Message) -> str:
        """List all configured MCP servers"""
        from config.settings import settings
        servers = settings.mcp_servers
        
        if not servers:
            return "📭 No MCP Servers configured currently."
            
        text = "📡 *CONFIGURED MCP SERVERS*\n⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
        for name, config in servers.items():
            cmd = config.get("command", "N/A")
            text += f"🔹 *{name}*: `{cmd}`\n"
            if config.get("args"):
                text += f"   └ Args: `{config['args']}`\n"
        return text

    async def _cmd_queue(self, args: list, msg: Message) -> str:
        """Show current action queue status"""
        if not self.agent or not self.agent.queue:
            return "❌ Queue system is not initialized."
            
        status = self.agent.queue.get_status()
        history = self.agent.queue.get_history(limit=5)
        
        text = "⚙️ *LANE QUEUE DASHBOARD*\n⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n\n"
        
        # Current Action
        current = status.get("current_action")
        if current:
            text += (
                f"⚡ *ACTIVE ACTION*\n"
                f"• ID: `{current['id'][:8]}`\n"
                f"• Type: `{current['action_type']}`\n"
                f"• Target: `{current['target_type']}:{current['target_id']}`\n"
                f"• Status: `PROCESSING` 🔄\n\n"
            )
        else:
            text += "⚡ *ACTIVE ACTION*: `IDLE` 💤\n\n"
            
        # Stats
        text += (
            f"📊 *QUEUE STATS*\n"
            f"• Pending Items: `{status['queue_size']}`\n"
            f"• History Size: `{status['history_size']}`\n"
            f"• State: `{'ACTIVE' if status['running'] else 'STOPPED'}`\n\n"
        )
        
        # Recent History
        if history:
            text += "📜 *RECENT EXECUTION*\n"
            for item in history:
                icon = "✅" if item["status"] == "completed" else "❌" if item["status"] == "failed" else "🚫"
                text += f"{icon} `{item['id'][:8]}`: {item['action_type']} - _{item['status']}_\n"
                
        return text

    async def _cmd_cancel(self, args: list, msg: Message) -> str:
        """Cancel a pending queue action: /cancel <id>"""
        if not args:
            return "⚠️ Usage: `/cancel <action_id_or_shortcut>`"
            
        action_id = args[0]
        if not self.agent or not self.agent.queue:
            return "❌ Queue system unavailable."
            
        # If shortcut (short id), we need to find the full id in history/pending
        # For simplicity, we assume full ID or we just mark it anyway
        success = await self.agent.queue.cancel_pending(action_id)
        
        if success:
            return f"🚫 *CANCELLED:* Action `{action_id}` has been marked for skip. I won't execute this command! 🛡️"
        else:
            return f"❌ Cannot cancel command `{action_id}` or command does not exist."
