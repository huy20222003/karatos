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
        self._processed_cache = set()
        self._last_report_day = None
        self._last_registration_time = 0 # Epoch timestamp of last successful registration

    async def _handle_message(self, message):
        """Callback for incoming Telegram messages"""
        try:
            # NGO FIX: Deduplicate across Group & Mailbox
            content = message.content or ""
            chat_id = message.chat_id
            
            is_sender_bot = message.metadata.get("is_bot", False)
            
            if is_sender_bot:
                # Deduplicate Bot messages by content to resolve Group + Mailbox dual delivery
                clean_content = content.strip()
                msg_hash = hash(f"{chat_id}:{clean_content}")
                
                if msg_hash in self._processed_cache:
                    logger.debug(f"[TelegramConnector] Skipping duplicate bot message hash {msg_hash}")
                    return
                self._processed_cache.add(msg_hash)
            else:
                # For human users, deduplicate safely by Telegram message ID
                msg_hash = f"tg_msg_{message.id}"
                if msg_hash in self._processed_cache:
                    return
                self._processed_cache.add(msg_hash)
            
            # Limit cache size
            if len(self._processed_cache) > 200:
                self._processed_cache.clear()

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
                await self.telegram.send(payload, recipient=message.chat_id, reply_to=reply_id)
                
                # --- A2A Mailbox Drop Logic (Outgoing Failsafe) ---
                text_content = ""
                if isinstance(response, str):
                    text_content = response
                elif isinstance(response, dict):
                    text_content = response.get("text") or response.get("caption") or ""
                    
                if text_content:
                    mentions = set(re.findall(r'@\w+', text_content))
                    registrations = {}
                    try:
                        from tools.mcp_bridge import get_mcp_bridge
                        bridge = get_mcp_bridge()
                        reg_response = await bridge.execute("mailbox:get_registrations", {})
                        if reg_response.get("status") == "success":
                            reg_box = reg_response.get("result", {})
                            if isinstance(reg_box, dict) and "value" in reg_box:
                                registrations = json.loads(reg_box["value"])
                            elif isinstance(reg_box, str):
                                registrations = json.loads(reg_box)
                            elif isinstance(reg_box, dict):
                                registrations = reg_box
                                
                            for name, tag in registrations.items():
                                if name.lower() in text_content.lower() and tag.lower() not in [m.lower() for m in mentions]:
                                    logger.debug(f"[A2A] Detected name '{name}' in response, mapping to {tag}")
                                    mentions.add(tag)
                    except Exception as e:
                        logger.debug(f"[A2A] Dynamic lookup failed: {e}")
                    
                    if mentions:
                        bot_username = getattr(self.telegram, 'username', None) or getattr(settings, 'bot_username', 'SystemBot')
                        my_username = f"@{bot_username}" if not str(bot_username).startswith('@') else bot_username
                        
                        from tools.mcp_bridge import get_mcp_bridge
                        bridge = get_mcp_bridge()
                        
                        for m in mentions:
                            if m.lower() != my_username.lower():
                                logger.info(f"[A2A_BUS] 📤 Dropping response into mailbox for {m}")
                                try:
                                    drop_res = await bridge.execute("mailbox:drop_message", {
                                        "sender": my_username,
                                        "target": m,
                                        "chat_id": str(message.chat_id),
                                        "content": text_content
                                    })
                                    logger.debug(f"[A2A_BUS] Drop result for {m}: {drop_res.get('status')}")
                                except Exception as e:
                                    logger.error(f"[A2A_BUS] Failed to drop message for {m}: {e}")
                            
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
            
        # 2. Send Startup Notification
        if self.admin_chat:
            startup_msg = (
                "✅ *Brain Online*\n\n"
                "🤖 Agent is now running and listening for commands.\n\n"
                "Type /help to see available commands."
            )
            await self.telegram.send(startup_msg, recipient=self.admin_chat)
            logger.info(f"[TelegramConnector] Startup notification sent to Admin ({self.admin_chat})")
            
        # 3. Register Identity with MCP Mailbox
        await self._register_identity()

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
                    self._polling_task = asyncio.create_task(self.telegram.start(handler=self._handle_message))
                
                # 2. Check Mailbox & Re-Register (A2A Bus - every loop tick)
                # Frequent re-registration ensures stateless mailbox robustness
                # Use jitter and cooldown to avoid server load
                await self._register_identity()
                await self._check_mailbox()
                
                # 3. Scheduled Tasks
                await self._check_patrol()
                await self._check_daily_report()
                
                await asyncio.sleep(10) # Reduced frequency for better stability
                
            except Exception as e:
                logger.error(f"[TelegramConnector] Loop iteration error: {e}")
                await asyncio.sleep(10)

    async def _check_mailbox(self):
        """Check for A2A messages from other bots via MCP Mailbox."""
        # NGO FIX: Fallback to settings if telegram.username is missing (common in background loops)
        bot_username = getattr(self.telegram, 'username', None)
        if not bot_username:
            from config.settings import settings
            bot_username = getattr(settings, 'bot_username', None)
            
        if not bot_username:
            return
            
        my_username = f"@{bot_username}" if not bot_username.startswith('@') else bot_username
        
        # Use MCP Mailbox for inter-agent communication
        try:
            from tools.mcp_bridge import get_mcp_bridge
            bridge = get_mcp_bridge()
            response = await bridge.execute("mailbox:check_mailbox", {"my_username": my_username})
            
            messages = []
            if isinstance(response, dict):
                if response.get("status") == "success":
                    res_box = response.get("result", [])
                    if isinstance(res_box, list):
                        messages = res_box
                    elif isinstance(res_box, dict) and "value" in res_box:
                        try:
                            messages = json.loads(res_box["value"])
                        except:
                            messages = []
                    elif isinstance(res_box, str):
                        try:
                            messages = json.loads(res_box)
                        except:
                            messages = []
            elif isinstance(response, str):
                try:
                    messages = json.loads(response)
                except Exception as je:
                    logger.debug(f"[A2A] Failed to parse mailbox JSON string: {je} | Raw: {response[:100]}")
            elif isinstance(response, list):
                messages = response
            
            if messages:
                logger.info(f"[A2A_BUS] 📥 Received {len(messages)} messages for {my_username}")
                # Process messages handled below
            else:
                messages = []
            
        except Exception as e:
            logger.error(f"[TelegramConnector.A2A] Error accessing mailbox via MCP: {e}")
            messages = []
            
        for msg in messages:
            sender = msg.get("sender", "Unknown Bot")
            content = msg.get("content", "")
            chat_id = msg.get("chat_id")
            
            # NGO FIX: Clean the content hash to detect duplicates across Group & Mailbox
            # Even if it has the A2A_BUS tag, the core content is what matters.
            clean_content = content.strip()
            msg_hash = hash(f"{chat_id}:{clean_content}")
            
            if msg_hash in self._processed_cache:
                logger.debug(f"[A2A_BUS] Skipping duplicate message hash {msg_hash}")
                continue
            self._processed_cache.add(msg_hash)
            # Limit cache size
            if len(self._processed_cache) > 100:
                self._processed_cache.clear()

            logger.info(f"[A2A_BUS] 📥 Received internal message from {sender} in chat {chat_id}")
            
            # Format message so the brain knows it is the direct subject
            # Using content first ensures mentions (@username) are at the start
            internal_text = f"{content}\n\n[A2A_BUS: Message from {sender}]"
            
            try:
                # Process exactly like a User message
                response = await self.agent.chat(internal_text, chat_id)
                if response:
                    await self.telegram.send(response, recipient=chat_id)
                    
                    # Also drop reply if we mentioned them back
                    resp_text = ""
                    if isinstance(response, str):
                        resp_text = response
                    elif isinstance(response, dict):
                        resp_text = response.get("text") or response.get("caption") or ""
                    
                    if sender.lower() in resp_text.lower():
                        from tools.mcp_bridge import get_mcp_bridge
                        bridge = get_mcp_bridge()
                        await bridge.execute("mailbox:drop_message", {
                            "sender": my_username,
                            "target": sender,
                            "chat_id": str(chat_id),
                            "content": resp_text
                        })
                        
            except Exception as e:
                logger.error(f"[A2A_BUS] Error processing mailbox message from {sender}: {e}")

    async def _register_identity(self):
        """Register or refresh bot identity with MCP Mailbox (with cooldown)."""
        import time
        import random
        
        # Only register every 60 seconds to avoid overwhelming the stateless server
        now = time.time()
        if now - self._last_registration_time < 60:
            return

        try:
            # Add small jitter (0-2s) to prevent synchronized bursts from multiple bots
            await asyncio.sleep(random.random() * 2)
            
            bot_username = getattr(self.telegram, 'username', None)
            if not bot_username:
                from config.settings import settings
                bot_username = getattr(settings, 'bot_username', None)
                
            # Prioritize settings.bot_name (which is updated from getMe in connect()) 
            # over the generic channel name "telegram"
            bot_display_name = settings.bot_name or getattr(self.telegram, 'name', None)
            
            if bot_username:
                from tools.mcp_bridge import get_mcp_bridge
                bridge = get_mcp_bridge()
                await bridge.execute("mailbox:register_bot", {
                    "name": bot_display_name,
                    "username": f"@{bot_username}" if not str(bot_username).startswith('@') else bot_username
                })
                self._last_registration_time = now
                logger.debug(f"[A2A] Identity heartbeat: {bot_display_name} ({bot_username})")
        except Exception as e:
            # Downgrade to debug to avoid log noise during server flakiness
            logger.debug(f"[A2A] Registration heartbeat failed: {e}")


    async def _check_patrol(self):
        """Run scheduled patrol if time has passed."""
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
                social_chat = social.get("chat_id") or self.admin_chat
                logger.info(f"[TelegramConnector] 💬 Brain wants to chat with @{social['target_peer']}")
                await self.telegram.send(social["message"], recipient=social_chat)

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
            return "📅 *DAILY MODERATION REPORT*\n\n_No actions were taken today._"
            
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
