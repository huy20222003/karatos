import asyncio
import re
import json
from datetime import datetime
from config.settings import settings
from channels.telegram.channel import TelegramChannel
from channels.telegram.handler import TelegramCommandHandler
from utils.logger import get_logger
from typing import Optional


logger = get_logger()

class TelegramConnector:
    """
    Modular connector for Telegram communication.
    Handles polling, patrol cycles, and daily reporting independently of the main entry point.
    """
    
    def __init__(self, agent):
        self.agent = agent
        self.telegram = TelegramChannel()
        self.handler = TelegramCommandHandler(agent=self.agent, channel=self.telegram)
        self.admin_chat = settings.telegram_chat_id
        self._running = False
        self._processed_hashes = set()
        self._last_report_day = None
        self._last_registration_time = 0 # Epoch timestamp of last successful registration

    async def _handle_message(self, message):
        """Callback for incoming Telegram messages"""
        try:
            # NGO FIX: Deduplicate incoming messages
            # This deduplication is a heuristic to prevent processing the same message multiple times
            # when it's delivered to both a group chat and a mailbox, or due to Telegram API retries.
            # For bots, we use content hash; for humans, Telegram message ID is more reliable.
            
            content = message.content or ""
            chat_id = message.chat_id
            
            is_sender_bot = message.metadata.get("is_bot", False)
            
            if is_sender_bot:
                # Deduplicate Bot messages by content to resolve Group + Mailbox dual delivery
                clean_content = content.strip()
                msg_hash = hash(f"{chat_id}:{clean_content}")
                
                if msg_hash in self._processed_hashes:
                    logger.debug(f"[TelegramConnector] Skipping duplicate bot message hash {msg_hash}")
                    return
                self._processed_hashes.add(msg_hash)
            else:
                # For human users, deduplicate safely by Telegram message ID
                msg_hash = f"tg_msg_{message.id}"
                if msg_hash in self._processed_hashes:
                    return
                self._processed_hashes.add(msg_hash)
            
            # Limit cache size
            if len(self._processed_hashes) > 200:
                self._processed_hashes.clear()

            response = await self.handler.handle(message)
            if response:
                # Allow the brain to control threading: if the response payload
                # specifies an explicit reply_to, honor it. Otherwise send as a
                # fresh message without forcing reply threading.
                reply_id = None
                payload = response
                if isinstance(response, dict):
                    reply_id = response.get("reply_to")
                    payload = {k: v for k, v in response.items() if k != "reply_to"}
                
                # B2B INTERCEPTION: Route response via Mailbox if replying to another bot
                replied_to_is_bot = message.metadata.get("replied_to_is_bot", False)
                replied_to_username = message.metadata.get("replied_to_username")
                
                my_username = getattr(self.telegram, 'username', None)
                
                if replied_to_is_bot and replied_to_username and replied_to_username != my_username:
                    try:
                        from tools.registry import get_tool_registry
                        registry = get_tool_registry()
                        
                        # Extract string content from payload
                        content_str = payload if isinstance(payload, str) else payload.get("text", str(payload))
                        
                        logger.info(f"[TelegramConnector] 📬 Cross-bot reply detected. Dropping copy to @{replied_to_username} via Mailbox.")
                        await asyncio.wait_for(registry.dispatch("mcp:mailbox:drop_message", {
                            "sender": my_username or "Karatos",
                            "target": f"@{replied_to_username}",
                            "chat_id": str(message.chat_id),
                            "content": content_str
                        }), timeout=5.0)
                    except Exception as e:
                        logger.error(f"[TelegramConnector] Failed to route cross-bot reply via Mailbox: {e}")
                
                # Fallback / Normal routing
                # Send the original message to Telegram
                await self.telegram.send(payload, recipient=message.chat_id, reply_to=reply_id)
                
                            
        except Exception as e:
            logger.error(f"[TelegramConnector] Error handling message: {e}")

    async def start(self):
        """Standard Telegram start sequence with health check."""
        self._running = True
        logger.info("[TelegramConnector] Starting communication layer...")
        
        # 1. Connect
        if not await self.telegram.connect():
            logger.error("[TelegramConnector] Failed to connect to Telegram.")
            return False
            
        # 1.5 Sync Identity back to Agent
        self.agent.refresh_identity()
        
        # 1.6 Register with Mailbox MCP
        await self._register_with_mailbox()
        
            
        # 2. Send Startup Notification (Brain-Powered)
        if self.admin_chat:
            await self._send_brain_greeting()
            logger.info(f"[TelegramConnector] Brain greeting sent to Admin ({self.admin_chat})")

        # 4. Start Main Loop
        try:
            await self._run_loop()
        except asyncio.CancelledError:
            logger.info("[TelegramConnector] Connector loop cancelled.")
        except Exception as e:
            logger.error(f"[TelegramConnector] Fatal loop error: {e}")
        finally:
            await self.stop()
            
        return True

    async def _run_loop(self):
        """Main internal loop for polling and scheduled tasks."""
        logger.info("[TelegramConnector] Entering main message loop.")
        
        while self._running:
            try:
                # 1. Poll for messages (Background Task)
                if not hasattr(self, "_polling_task") or self._polling_task.done():
                    logger.info("[TelegramConnector] Spawning polling task.")
                    # Main polling task
                    self._polling_task = asyncio.create_task(
                        self.telegram.start(handler=self._handle_message),
                        name="TelegramCollector_Loop"
                    )
                
                # 3. Scheduled Tasks
                await self._check_patrol()
                await self._check_daily_report()
                
                await asyncio.sleep(10) # Reduced frequency for better stability
                
            except Exception as e:
                logger.error(f"[TelegramConnector] Loop iteration error: {e}")
                await asyncio.sleep(10)

    async def _send_brain_greeting(self):
        """Generate and send a natural greeting using the Brain model."""
        try:
            from core.brain.model import BrainModel
            from core.brain.prompts.registry import get_prompt_registry
            from core.identity import AgentIdentity
            
            identity = AgentIdentity()
            # Use current mood and energy if available, or defaults
            mood = getattr(self.agent.brain, 'mood', 'OPTIMISTIC')
            energy = getattr(self.agent.brain, 'energy_level', 1.0)
            
            import random
            from datetime import datetime
            current_time = datetime.now().strftime("%H:%M %A")
            
            from utils.language import language_for_prompt, normalize_language_code
            lang_cfg = getattr(settings, "user_language", None) or "English"
            language = language_for_prompt(normalize_language_code(lang_cfg, default="English"), default="English")
            
            prompt = get_prompt_registry().get(
                "system.social_impulse.social_impulse",
                bot_name=identity.name,
                peer="Commander", # Addressing the admin
                peer_type="Founder / Administrator",
                mood=mood,
                current_time=current_time,
                impulse_type="STARTUP_GREETING",
                source_material="I have just finished starting up and am ready to assist. I want to send a warm and professional greeting. IMPORTANT: Do NOT include any mentions, tags, or @ symbols (e.g., no @Commander). Just speak naturally.",
                language=language,
            )

            model = BrainModel(mode="social")
            response = await model.think(prompt, phase="startup", timeout=60.0)
            
            if response and response not in ["ERROR_TIMEOUT", "ERROR_FAILED"]:
                from core.brain.utils import strip_thinking_tags
                message = strip_thinking_tags(response).strip().strip('"').strip("'")
                
                # Append a small status indicator
                message = f"🟢 {message}"
                
                await self.telegram.send(message, recipient=self.admin_chat)
            else:
                # Fallback to a simple message if brain fails
                await self.telegram.send("✅ *System is ready.* I am online and awaiting your orders.", recipient=self.admin_chat)
        except Exception as e:
            logger.error(f"[TelegramConnector] Failed to send brain greeting: {e}")
            await self.telegram.send("✅ Brain Online.", recipient=self.admin_chat)

    async def _register_with_mailbox(self):
        """Register bot identity with the Mailbox MCP server."""
        try:
            from core.identity import AgentIdentity
            from tools.registry import get_tool_registry
            
            identity = AgentIdentity()
            name = identity.active_name or settings.bot_name or "Karatos"
            username = settings.bot_username or "@karatos_bot"
            
            logger.info(f"[TelegramConnector] Registering with Mailbox: {name} ({username})")
            
            registry = get_tool_registry()
            # Explicitly use mcp:mailbox:register_bot
            result = await registry.dispatch("mcp:mailbox:register_bot", {
                "name": name,
                "username": username
            })
            
            if result.get("status") == "success":
                logger.info(f"[TelegramConnector] Mailbox registration successful: {result.get('result')}")
            else:
                logger.warning(f"[TelegramConnector] Mailbox registration failed: {result.get('message')}")
                
        except Exception as e:
            logger.debug(f"[TelegramConnector] Error during Mailbox registration: {e}")


    async def _poll_mailbox(self):
        """Poll the Mailbox MCP for new messages and process them."""
        try:
            from tools.registry import get_tool_registry
            registry = get_tool_registry()
            
            username = settings.bot_username or "@karatos_bot"
            name = settings.bot_name or "Karatos"
            
            # Check for both handle and name
            for identifier in [username, name]:
                if not identifier: continue
                
                try:
                    # Timeout to prevent hanging on network issues
                    result = await asyncio.wait_for(
                        registry.dispatch("mcp:mailbox:check_mailbox", {"my_username": identifier}),
                        timeout=5.0
                    )
                    
                    if result.get("status") == "success":
                        import json
                        try:
                            # result.get("data") contains raw JSON string from server
                            raw_data = result.get("data", "[]")
                            messages = json.loads(raw_data)
                            if messages:
                                logger.info(f"[TelegramConnector] 📬 Received {len(messages)} messages from Mailbox for {identifier}")
                                for msg in messages:
                                    await self._process_mailbox_message(msg)
                        except Exception as e:
                            logger.error(f"[TelegramConnector] Failed to parse mailbox messages: {e}")
                except asyncio.TimeoutError:
                    logger.debug(f"[TelegramConnector] Mailbox poll timeout for {identifier}")
                except Exception as e:
                    logger.error(f"[TelegramConnector] Mailbox poll error for {identifier}: {e}")
                        
        except Exception as e:
            logger.debug(f"[TelegramConnector] Mailbox polling error: {e}")

    async def _process_mailbox_message(self, msg: dict):
        """Inject a mailbox message into the agent's chat for processing."""
        sender = msg.get("sender", "Unknown")
        content = msg.get("content", "")
        chat_id = msg.get("chat_id") or self.admin_chat
        
        logger.info(f"[TelegramConnector] 📩 Processing peer message from {sender}")
        
        # Format as a system-injected message to the agent
        formatted_msg = f"[BOT_MAILBOX] Message from {sender}:\n\n{content}"
        
        # Send to Telegram (Admin) so the user sees it too
        if self.admin_chat:
             await self.telegram.send(f"📬 *New Mailbox Message*\nFrom: `{sender}`\n\n{content}", recipient=self.admin_chat)
        
        # Inject into Brain for autonomous response
        # Using a named task so it's visible in cleanup diagnostics
        asyncio.create_task(
            self.agent.chat(formatted_msg, chat_id=str(chat_id)),
            name=f"MailboxProcessor_{sender}_{datetime.utcnow().timestamp()}"
        )

    # _check_mailbox removed in Brain 2.6 in favor of Direct Agent RPC


    async def _check_patrol(self):
        """Run scheduled patrol if time has passed and check mailbox."""
        # 1. Check Mailbox for incoming peer messages (High Priority)
        await self._poll_mailbox()

        # 2. Daily Report
        await self._check_daily_report()

        # 3. Braing Patrol
        now = datetime.utcnow()
        last_patrol = getattr(self.agent, "_last_patrol_time", None)
        
        # Default 10 mins if not set
        interval = settings.scan_interval_minutes
        
        if last_patrol is None or (now - last_patrol).total_seconds() >= (interval * 60):
            logger.info(f"[TelegramConnector] Triggering scheduled patrol (Interval: {interval}m)")
            self.agent._last_patrol_time = now
            
            await self.telegram.send("🔍 Starting scheduled patrol...", recipient=self.admin_chat)
            final_state = await self.agent.patrol()
            await self.telegram.send("✅ Patrol cycle complete. Actions queued autonomously.", recipient=self.admin_chat)
            
            # Proactive Chat
            goals = final_state.get("goals", [])
            if goals:
                await self.telegram.initiate_proactive_chat(
                    goals=goals,
                    mood=final_state.get("mood", "OPTIMISTIC"),
                    energy=final_state.get("energy_level", 1.0)
                )
            
            # Social Impulse — brain's emergent desire to chat with a peer
            social = final_state.get("social_impulse")
            if social:
                target_peer = social.get("target_peer", "")
                message = social.get("message", "")
                social_chat = social.get("chat_id") or self.admin_chat
                
                logger.info(f"[TelegramConnector] 💬 Brain wants to chat with {target_peer}")
                
                # If target starts with @ and it's not the admin, or if flagged as bot
                # For now, if we have mailbox and it's a bot-like target, use mailbox
                if target_peer.startswith("@") and target_peer != settings.telegram_chat_id:
                     try:
                         from tools.registry import get_tool_registry
                         registry = get_tool_registry()
                         logger.info(f"[TelegramConnector] 📬 Dropping social impulse into Mailbox for {target_peer}")
                         await registry.dispatch("mcp:mailbox:drop_message", {
                             "sender": settings.bot_name or "Karatos",
                             "target": target_peer,
                             "chat_id": str(social_chat),
                             "content": message
                         })
                     except Exception as e:
                         logger.error(f"[TelegramConnector] Mailbox routing failed: {e}")
                         await self.telegram.send(message, recipient=social_chat)
                else:
                    await self.telegram.send(message, recipient=social_chat)

    async def _check_daily_report(self):
        """Generate and send daily report at 23:00 UTC."""
        now = datetime.utcnow()
        if now.hour == 23 and self._last_report_day != now.day:
            logger.info("[TelegramConnector] Generating daily moderation report...")
            self._last_report_day = now.day
            
            actions = await self.agent.memory.get_daily_actions(hours=24)
            report_msg = self._build_report_message(actions)
            await self.telegram.send(report_msg, recipient=self.admin_chat)

    def _build_report_message(self, actions: list) -> str:
        if not actions:
            return "📅 *DAILY MODERATION REPORT*\n\n No actions were taken today."
            
        msg = "📅 *DAILY ANOMALY REPORT (UTC)*\n\n"
        
        for i, a in enumerate(actions, 1):
            msg += f"{i}. *{a['action']}* on `{a['target_id']}`\n"
            msg += f"   └ Reason: _{a['reason']}_\n\n"
            
        msg += f"📊 *Total occurrences:* `{len(actions)}`"
        return msg

    async def stop(self):
        """Graceful shutdown of Telegram communication."""
        self._running = False
        logger.info("[TelegramConnector] Stopping...")
        if hasattr(self, "_polling_task"):
            self._polling_task.cancel()
        await self.telegram.disconnect()
