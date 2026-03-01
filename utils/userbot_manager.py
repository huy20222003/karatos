import asyncio
import logging
import re
from typing import Dict, List, Optional, Union
from telethon import TelegramClient, functions, types
from config.settings import settings
from utils.logger import get_logger

logger = get_logger()

class UserbotManager:
    """
    Manager for Telegram Userbot (Client API) to handle dynamic discovery.
    """
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(UserbotManager, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
            
        self.api_id = settings.telegram_api_id
        self.api_hash = settings.telegram_api_hash
        self.session_name = settings.telegram_userbot_session
        self.client: Optional[TelegramClient] = None
        self._initialized = True

    async def start(self):
        """Start the Telegram Client."""
        if not self.api_id or not self.api_hash:
            logger.warning("[USERBOT] API_ID or API_HASH not configured. Userbot discovery disabled.")
            return False

        try:
            self.client = TelegramClient(self.session_name, self.api_id, self.api_hash)
            await self.client.start()
            logger.info("[USERBOT] Userbot started successfully.")
            return True
        except Exception as e:
            logger.error(f"[USERBOT] Failed to start Userbot: {e}")
            return False

    async def send_message(self, agent_id: Union[str, int], text: str) -> bool:
        """Send a standard Telegram message to an agent."""
        if not self.client or not self.client.is_connected():
            success = await self.start()
            if not success: return False
            
        try:
            await self.client.send_message(agent_id, text)
            logger.info(f"[USERBOT] Sent message to {agent_id}")
            return True
        except Exception as e:
            logger.error(f"[USERBOT] Failed to send message to {agent_id}: {e}")
            return False

    async def get_agents_from_group(self, group_id: Optional[Union[str, int]] = None) -> Dict[str, dict]:
        """
        Scan a group for bots and extract their descriptions.
        Returns a mapping of {agent_name: {"id": telegram_id, "description": bio, "tag": "@username"}}.
        """
        import sys
        target_group = group_id or settings.telegram_discovery_group_id
        if not target_group or not self.client:
            return {}

        agents = {}
        try:
            # First, get dialogs to warm the cache (Critical for Telethon)
            try:
                dialogs = await self.client.get_dialogs(limit=500)
            except Exception as e:
                logger.warning(f"[USERBOT] Failed to fetch dialogs: {e}")
                dialogs = []

            scan_target = None
            target_str = str(target_group).strip().lower()
            
            for d in dialogs:
                if str(d.id) == target_str or \
                   target_str.replace("-100", "") == str(d.id).replace("-100", "") or \
                   (hasattr(d, 'title') and d.title and d.title.lower() == target_str):
                    scan_target = d.entity
                    break
            
            if not scan_target:
                try:
                    scan_target = await self.client.get_entity(target_group)
                except:
                    if target_str.replace("-", "").isdigit() and not target_str.startswith("-100"):
                        try:
                            alt_id = int("-100" + target_str.replace("-", ""))
                            scan_target = await self.client.get_entity(alt_id)
                        except: pass

            if not scan_target:
                logger.error(f"[USERBOT] Could not resolve group {target_group}")
                return {}

            # Now scan participants
            async for user in self.client.iter_participants(scan_target):
                if user.bot:
                    agent_name = (user.username or user.first_name or f"bot_{user.id}").lower()
                    
                    try:
                        full_user = await self.client(functions.users.GetFullUserRequest(id=user.id))
                        description = full_user.full_user.about or "Telegram Bot Agent."
                    except:
                        description = "Telegram Bot Agent."
                    
                    agents[agent_name] = {
                        "id": user.id,
                        "username": user.username,
                        "description": description,
                        "tag": f"@{user.username}" if user.username else f"ID:{user.id}",
                        "is_bot": True
                    }
                    logger.info(f"[USERBOT] Discovered agent: {agent_name}")
            
            return agents
        except Exception as e:
            logger.error(f"[USERBOT] Error scanning group {target_group}: {e}")
            return {}

    async def stop(self):
        if self.client:
            await self.client.disconnect()
            logger.info("[USERBOT] Userbot disconnected.")

_manager = None

def get_userbot_manager() -> UserbotManager:
    global _manager
    if _manager is None:
        _manager = UserbotManager()
    return _manager
