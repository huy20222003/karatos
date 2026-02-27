import os
import yaml
import time
from pathlib import Path
from typing import Dict, Any, Optional
from utils.logger import get_logger

logger = get_logger()

class PromptRegistry:
    """
    Centralized registry for managing Brain prompts.
    Loads prompts from YAML/Markdown files and supports hot-reloading.
    """
    _instance = None
    _prompts: Dict[str, str] = {}
    _hashes: Dict[str, str] = {}
    _last_reload_ts: float = 0.0
    
    # Path settings (Dynamic resolution relative to this file's parent)
    PROMPT_ROOT = Path(__file__).parent.parent.parent.parent / "prompts"
    # Best-effort hot reload: re-scan prompts at most this often.
    # (load_all uses MD5 caching, so unchanged files are cheap.)
    HOT_RELOAD_INTERVAL_SECONDS = 2.0

    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(PromptRegistry, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        self.load_all()
        self._last_reload_ts = time.time()
        self._initialized = True

    def load_all(self):
        """Walk through the prompt directory and load all .yaml and .md files."""
        if not self.PROMPT_ROOT.exists():
            logger.warning(f"[PromptRegistry] Root directory {self.PROMPT_ROOT} does not exist.")
            return

        # IMPORTANT: Do NOT clear _prompts here.
        # We use MD5 caching to skip unchanged files; clearing would drop previously
        # loaded prompts and leave the registry incomplete after a hot reload.
        for file_path in self.PROMPT_ROOT.rglob("*"):
            if not file_path.is_file():
                continue
                
            # MD5 verification to avoid redundant parsing
            import hashlib
            try:
                current_hash = hashlib.md5(file_path.read_bytes()).hexdigest()
                if self._hashes.get(str(file_path)) == current_hash:
                    continue # Skip unchanged file
                
                self._hashes[str(file_path)] = current_hash
                if file_path.suffix in [".yaml", ".yml"]:
                    self._load_yaml(file_path)
                elif file_path.suffix == ".md":
                    self._load_markdown(file_path)
            except Exception as e:
                logger.error(f"[PromptRegistry] Hash check failed for {file_path}: {e}")
        
        self._last_reload_ts = time.time()
        logger.debug(f"[PromptRegistry] Loaded {len(self._prompts)} prompt templates.")

    def _load_yaml(self, path: Path):
        """Load prompts from a YAML file with recursive flattening."""
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
                if isinstance(data, dict):
                    # Base prefix from file path: e.g. system.system_alerts
                    file_prefix = ".".join(path.relative_to(self.PROMPT_ROOT).with_suffix("").parts)
                    self._flatten_and_store(data, file_prefix)
        except Exception as e:
            logger.error(f"[PromptRegistry] Error loading YAML {path}: {e}")

    def _flatten_and_store(self, data: Any, prefix: str):
        """Recursively flatten dictionary keys."""
        if isinstance(data, dict):
            for key, val in data.items():
                # Handle 'root' special case or nested keys
                new_key = prefix if key == "root" else f"{prefix}.{key}"
                self._flatten_and_store(val, new_key)
        else:
            # Base case: store the value (should be a string or formatted prompt)
            self._prompts[prefix] = data

    def _load_markdown(self, path: Path):
        """Load a prompt from a Markdown file (the whole file is the prompt)."""
        try:
            with open(path, "r", encoding="utf-8") as f:
                key = ".".join(path.relative_to(self.PROMPT_ROOT).with_suffix("").parts)
                self._prompts[key] = f.read().strip()
        except Exception as e:
            logger.error(f"[PromptRegistry] Error loading Markdown {path}: {e}")

    def get(self, key: str, **kwargs) -> str:
        """Get a prompt by key and format it with provided variables."""
        # Hot reload support for long-running processes (Telegram connector).
        # Rate-limited to avoid scanning on every call.
        try:
            now = time.time()
            if now - float(getattr(self, "_last_reload_ts", 0.0)) >= float(self.HOT_RELOAD_INTERVAL_SECONDS):
                self.load_all()
        except Exception as e:
            logger.debug(f"[PromptRegistry] Hot reload skipped: {e}")

        template = self._prompts.get(key)
        if not template:
            logger.error(f"[PromptRegistry] Prompt key not found: {key}")
            return f"PROMPT_NOT_FOUND: {key}"
        
        if not isinstance(template, str):
            return template

        # Inject standard identity variables if missing
        from config.settings import settings
        from datetime import datetime
        
        standard_vars = {
            "bot_name": getattr(settings, "bot_name", "Brain"),
            "bot_username": getattr(settings, "bot_username", "bot"),
            "user_pronoun": getattr(settings, "user_pronoun", "Anh"),
            "bot_pronoun": getattr(settings, "bot_pronoun", "Em"),
            "mood": "OPTIMISTIC",
            "current_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        
        for k, v in standard_vars.items():
            if k not in kwargs:
                kwargs[k] = v
        
        import re
        try:
            # Safer formatting: Only replace keys that are actually in kwargs.
            # This prevents KeyErrors when the template or injected text contains curly braces {}.
            formatted = template
            for key, val in kwargs.items():
                # Replace {key} with val
                # Using lambda to avoid issues with backslashes in value
                pattern = re.compile(re.escape('{' + key + '}'))
                formatted = pattern.sub(lambda _: str(val), formatted)
            return formatted
        except Exception as e:
            logger.error(f"[PromptRegistry] Error formatting prompt {key}: {e}")
            return template

# Singleton helper
_registry = None
def get_prompt_registry():
    global _registry
    if _registry is None:
        _registry = PromptRegistry()
    return _registry
