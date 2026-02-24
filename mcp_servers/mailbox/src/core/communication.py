from typing import Dict, List, Union
from ..schemas.messaging import MailboxMessage

from ..config import settings

class CommunicationManager:
    """Manages bot communication, broadcasting, and identity resolution."""
    
    def __init__(self):
        # {target_username: [MailboxMessage]}
        self.mailbox_store: Dict[str, List[MailboxMessage]] = {}
        
        # {name_lower: username} - Identity Registry (Dynamically populated via register_bot)
        self.identity_registry: Dict[str, str] = {}
        
        self.MAX_MESSAGES_PER_BOT = settings.MAX_MESSAGES_PER_BOT
        self.storage_path = "registrations.json"
        self._load_registrations()

    def _load_registrations(self):
        import json
        import os
        if os.path.exists(self.storage_path):
            try:
                with open(self.storage_path, "r", encoding="utf-8") as f:
                    self.identity_registry = json.load(f)
                print(f"[CORE] Loaded {len(self.identity_registry)} registrations from storage")
            except Exception as e:
                print(f"[CORE] Error loading registrations: {e}")

    def _save_registrations(self):
        import json
        try:
            with open(self.storage_path, "w", encoding="utf-8") as f:
                json.dump(self.identity_registry, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"[CORE] Error saving registrations: {e}")

    def register_identity(self, name: str, username: str):
        self.identity_registry[name.lower()] = username
        if not username.startswith('@'):
            username = f"@{username}"
        self.identity_registry[username.lower()] = username
        self._save_registrations()

    def get_registrations(self) -> Dict[str, str]:
        """Returns only the Name -> Username mappings (excluding the username keys)."""
        return {k: v for k, v in self.identity_registry.items() if not k.startswith('@')}

    def resolve_target(self, target: str) -> str:
        target_clean = target.lower().strip()
        # 1. Exact match (Account ID or specific name)
        if target_clean in self.identity_registry:
            return self.identity_registry[target_clean]
        
        # 2. Fuzzy/Substring match for names
        # Check if the target is contained within any registered name (e.g. "Sentry" matches "Sentry (Little Niva)")
        for name_lower, username in self.identity_registry.items():
            if not name_lower.startswith('@') and target_clean in name_lower:
                return username
            
        # 3. Default to @username format
        result = target_clean
        if not target_clean.startswith('@'):
            result = f"@{target_clean}"
        
        return result

    def drop_message(self, sender: str, targets: Union[str, List[str]], chat_id: str, content: str) -> List[str]:
        if isinstance(targets, str):
            if "," in targets:
                target_list = [t.strip() for t in targets.split(",")]
            else:
                target_list = [targets.strip()]
        else:
            target_list = targets

        sender_tag = self.resolve_target(sender)
        successful_targets = []

        for raw_target in target_list:
            if not raw_target:
                continue
                
            standard_target = self.resolve_target(raw_target)
            
            message = MailboxMessage(
                sender=sender_tag,
                target=standard_target,
                chat_id=str(chat_id),
                content=content
            )

            if standard_target not in self.mailbox_store:
                self.mailbox_store[standard_target] = []
            
            self.mailbox_store[standard_target].append(message)
            
            if len(self.mailbox_store[standard_target]) > self.MAX_MESSAGES_PER_BOT:
                self.mailbox_store[standard_target] = self.mailbox_store[standard_target][-self.MAX_MESSAGES_PER_BOT:]
            
            successful_targets.append(standard_target)
            print(f"[CORE] 📬 Message from {sender_tag} for {standard_target}")

        return successful_targets

    def consume_messages(self, my_username: str) -> List[dict]:
        standard_username = self.resolve_target(my_username)
        messages = self.mailbox_store.pop(standard_username, [])
        if messages:
            print(f"[CORE] 📥 Consumed {len(messages)} messages for {standard_username}")
        return [msg.model_dump() for msg in messages]
