"""
Credential Manager Tool
Secure VAULT storage for service tokens and API keys using Fernet encryption.
"""
import os
import json
from datetime import datetime
from typing import Dict, Any, List, Optional

from utils.logger import get_logger
from utils.crypto import encrypt_text, decrypt_text

logger = get_logger()


class CredentialManager:
    """Manages encrypted credentials in the VAULT memory category."""

    VAULT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "storage", "vault")

    @classmethod
    def _ensure_dir(cls):
        os.makedirs(cls.VAULT_DIR, exist_ok=True)

    @classmethod
    def _get_path(cls, name: str) -> str:
        safe_name = name.lower().replace(" ", "_").replace("/", "_")
        return os.path.join(cls.VAULT_DIR, f"{safe_name}.json")

    @classmethod
    def store_credential(cls, name: str, service: str, token: str,
                         notes: str = "") -> Dict[str, Any]:
        """Encrypt and store a credential."""
        cls._ensure_dir()

        encrypted_token = encrypt_text(token)

        entry = {
            "name": name,
            "service": service,
            "token": encrypted_token,
            "notes": notes,
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
        }

        path = cls._get_path(name)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(entry, f, indent=2, ensure_ascii=False)

        logger.info(f"[VAULT] Stored credential: {name} ({service})")
        return {"status": "success", "message": f"Credential '{name}' stored securely."}

    @classmethod
    def list_credentials(cls) -> List[Dict[str, str]]:
        """List all stored credentials (names and services only)."""
        cls._ensure_dir()
        creds = []

        for filename in sorted(os.listdir(cls.VAULT_DIR)):
            if not filename.endswith(".json"):
                continue
            try:
                path = os.path.join(cls.VAULT_DIR, filename)
                with open(path, "r", encoding="utf-8") as f:
                    entry = json.load(f)
                creds.append({
                    "name": entry.get("name", filename[:-5]),
                    "service": entry.get("service", "unknown"),
                    "notes": entry.get("notes", ""),
                    "created_at": entry.get("created_at", ""),
                })
            except:
                continue

        return creds

    @classmethod
    def get_credential(cls, name: str) -> Optional[str]:
        """Decrypt and return a credential token (internal use only)."""
        path = cls._get_path(name)
        if not os.path.exists(path):
            return None

        try:
            with open(path, "r", encoding="utf-8") as f:
                entry = json.load(f)
            encrypted_token = entry.get("token", "")
            return decrypt_text(encrypted_token)
        except Exception as e:
            logger.error(f"[VAULT] Failed to decrypt credential '{name}': {e}")
            return None

    @classmethod
    def revoke_credential(cls, name: str) -> Dict[str, Any]:
        """Delete a credential from the VAULT."""
        path = cls._get_path(name)
        if not os.path.exists(path):
            return {"status": "error", "message": f"Credential '{name}' not found."}

        os.remove(path)
        logger.info(f"[VAULT] Revoked credential: {name}")
        return {"status": "success", "message": f"Credential '{name}' revoked."}
