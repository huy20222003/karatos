"""
Secure Configuration Manager
Stores user-editable settings in an encrypted JSON file (secure_config.enc.json).
Values are encrypted with Fernet (same MEMORY_KEY as memory encryption).

ALL imports are lazy to avoid circular dependency with settings.py.
"""
import os
import json
from typing import Any, Dict

_CONFIG_DIR = os.path.dirname(__file__)
CONFIG_PATH = os.path.abspath(os.path.join(_CONFIG_DIR, "secure_config.enc.json"))

# ── Fields managed here (editable via GUI, encrypted at rest) ──
MANAGED_FIELDS = {
    # Database
    "database_url",
    # LLM Provider & Models
    "llm_provider", "ollama_base_url", "ollama_model_name", "ollama_vision_model_name",
    "openai_api_key", "openai_api_base", "openai_model_name",
    "anthropic_api_key", "anthropic_model_name",
    "deepseek_api_key", "deepseek_model_name",
    "claude_web_model_name", "claude_web_endpoint", "claude_web_timeout_seconds", "claude_web_port",
    # Model Parameters
    "model_temperature", "model_max_tokens", "model_context_size",
    "model_threads", "model_parallelism",
    # Agent Behavior
    "scan_interval_minutes", "rolling_window_hours",
    "max_actions_per_hour", "action_cooldown_minutes",
    "failure_streak_threshold", "human_approval_required",
    # Context
    "user_language", "context_planning_limit", "context_generation_limit",
    # Identity
    "bot_name", "user_pronoun", "bot_pronoun",
    # Telegram
    "telegram_bot_token", "telegram_chat_id", "telegram_polling_timeout",
    # External API Keys
    "tavily_api_key", "resend_api_key", "resend_from_email",
    "cloudinary_cloud_name", "cloudinary_api_key", "cloudinary_api_secret",
    # Audio
    "whisper_model_size",
    # System Ports
    "dashboard_port",
}


# ═══════════════════════════════════════════════
#  Core Read / Write  (all imports lazy)
# ═══════════════════════════════════════════════

def load() -> Dict[str, str]:
    """Load and decrypt all config values from JSON file."""
    if not os.path.exists(CONFIG_PATH):
        return {}
    try:
        from utils.crypto import decrypt_text
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            encrypted_data = json.load(f)
        result = {}
        for key, enc_value in encrypted_data.items():
            try:
                result[key] = decrypt_text(enc_value)
            except Exception:
                result[key] = enc_value  # plaintext fallback
        return result
    except Exception as e:
        print(f"[SECURE_CONFIG] Failed to load: {e}")
        return {}


def save(data: Dict[str, str]):
    """Encrypt and persist all config values to JSON file."""
    from utils.crypto import encrypt_text
    encrypted = {}
    for key, value in data.items():
        try:
            encrypted[key] = encrypt_text(str(value))
        except Exception:
            encrypted[key] = str(value)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(encrypted, f, indent=2, ensure_ascii=False)
    print(f"[SECURE_CONFIG] Saved {len(data)} encrypted values to secure_config.enc.json")


def get_all() -> Dict[str, Any]:
    """Get all decrypted config values with correct Python types."""
    return {k: _cast(k, v) for k, v in load().items()}


def get(key: str, default: Any = None) -> Any:
    """Get a single decrypted value."""
    data = load()
    return _cast(key, data[key]) if key in data else default


def update(updates: Dict[str, Any]):
    """Merge updates into existing config (only MANAGED_FIELDS allowed)."""
    data = load()
    for key, value in updates.items():
        if key in MANAGED_FIELDS:
            data[key] = str(value)
    save(data)


def delete(key: str):
    """Remove a key."""
    data = load()
    if key in data:
        del data[key]
        save(data)


def exists() -> bool:
    """Check if encrypted config file exists."""
    return os.path.exists(CONFIG_PATH)


def _cast(key: str, value: str) -> Any:
    """Helper to cast string values from storage back to correct Python types."""
    if value is None:
        return None
    val_lower = str(value).lower()

    # Booleans
    if val_lower in ("true", "yes", "on"): return True
    if val_lower in ("false", "no", "off"): return False

    # Numbers
    try:
        # Check if it should be an int (no decimal point)
        if "." not in value:
            return int(value)
        return float(value)
    except (ValueError, TypeError):
        pass

    return value


# ═══════════════════════════════════════════════
#  GUI helpers
# ═══════════════════════════════════════════════

_SECRET_PATTERNS = {"api_key", "token", "secret", "password"}


def get_safe_view() -> Dict[str, Any]:
    """Return config for GUI display — secrets masked, others plain."""
    data = get_all()
    result = {}
    for key, value in data.items():
        is_secret = any(p in key.lower() for p in _SECRET_PATTERNS)
        if is_secret and value:
            result[key] = {"value": "●●●●●●●●  (configured)", "masked": True}
        else:
            result[key] = {"value": value, "masked": False}
    return result
