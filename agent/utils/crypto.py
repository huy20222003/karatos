"""
NivaBrain Memory Encryption (Fernet AES-128-CBC)
Provides transparent encrypt/decrypt for Markdown memory files.
Only the agent (with the key from .env) can read the stored memories.
"""
import os
import base64
from cryptography.fernet import Fernet
from config.settings import settings
from utils.logger import get_logger

logger = get_logger()

# Singleton cipher instance
_cipher: Fernet = None

def _get_or_create_key() -> bytes:
    """Load encryption key from settings/env, or generate and persist one."""
    key = settings.memory_key
    
    if key:
        return key.encode()
    
    # Auto-generate on first run
    new_key = Fernet.generate_key()
    logger.info("[CRYPTO] No MEMORY_KEY found. Generating new encryption key...")
    
    # Persist to .env
    env_path = os.path.join(os.path.dirname(__file__), "..", ".env")
    try:
        with open(env_path, "a", encoding="utf-8") as f:
            f.write(f"\n# Memory Encryption (Auto-generated - DO NOT SHARE)\nMEMORY_KEY={new_key.decode()}\n")
        logger.info(f"[CRYPTO] Key saved to .env. Keep this file secure!")
    except Exception as e:
        logger.error(f"[CRYPTO] Failed to persist key to .env: {e}")
    
    # Also set in current process
    os.environ["MEMORY_KEY"] = new_key.decode()
    return new_key


def get_cipher() -> Fernet:
    """Get the singleton Fernet cipher."""
    global _cipher
    if _cipher is None:
        key = _get_or_create_key()
        _cipher = Fernet(key)
    return _cipher


def encrypt_text(plaintext: str) -> str:
    """Encrypt a string and return base64-encoded ciphertext."""
    if not plaintext:
        return ""
    cipher = get_cipher()
    encrypted = cipher.encrypt(plaintext.encode("utf-8"))
    return base64.urlsafe_b64encode(encrypted).decode("ascii")


def decrypt_text(ciphertext: str) -> str:
    """Decrypt a base64-encoded ciphertext back to string."""
    if not ciphertext:
        return ""
    try:
        cipher = get_cipher()
        raw = base64.urlsafe_b64decode(ciphertext.encode("ascii"))
        return cipher.decrypt(raw).decode("utf-8")
    except Exception as e:
        # If decryption fails, it might be plaintext (migration period)
        logger.debug(f"[CRYPTO] Decryption failed (possibly plaintext): {e}")
        return ciphertext


def encrypt_file(file_path: str):
    """Encrypt an entire file in-place."""
    if not os.path.exists(file_path):
        return
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            plaintext = f.read()
        
        # Skip if already encrypted (starts with marker)
        if plaintext.startswith("ENC::"):
            return
        
        encrypted = encrypt_text(plaintext)
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(f"ENC::{encrypted}")
        
        logger.debug(f"[CRYPTO] Encrypted: {file_path}")
    except Exception as e:
        logger.error(f"[CRYPTO] Failed to encrypt {file_path}: {e}")


def decrypt_file(file_path: str) -> str:
    """Read and decrypt a file. Returns plaintext content."""
    if not os.path.exists(file_path):
        return ""
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
        
        # If encrypted, strip marker and decrypt
        if content.startswith("ENC::"):
            return decrypt_text(content[5:])
        
        # Plaintext (not yet encrypted / migration)
        return content
    except Exception as e:
        logger.error(f"[CRYPTO] Failed to read {file_path}: {e}")
        return ""


def write_encrypted(file_path: str, plaintext: str, mode: str = "w"):
    """Write content to a file in encrypted form."""
    try:
        if mode == "a" and os.path.exists(file_path):
            # Decrypt existing, append, then re-encrypt
            existing = decrypt_file(file_path)
            plaintext = existing + plaintext
        
        encrypted = encrypt_text(plaintext)
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(f"ENC::{encrypted}")
        
        logger.debug(f"[CRYPTO] Written encrypted: {file_path}")
    except Exception as e:
        logger.error(f"[CRYPTO] Failed to write encrypted {file_path}: {e}")
