"""
Language Utility
Provides normalization and prompt-friendly formatting for language signals.
"""

from __future__ import annotations

from typing import Optional


def normalize_language_code(code: Optional[str], default: str = "Vietnamese") -> str:
    """
    Normalize a language code or name coming from InputPipeline/LLM/user settings.

    - Supports common names (Vietnamese, English, etc.) and codes (vi, en).
    - Falls back to `default` when missing or invalid.
    """
    if not code:
        return default

    raw = str(code).strip()
    if not raw:
        return default

    lowered = raw.lower()
    
    # Map common codes to full names or just return the capitalized name
    mapping = {
        "vi": "Vietnamese",
        "en": "English",
        "mixed": "Vietnamese",
        "unknown": default
    }
    
    if lowered in mapping:
        return mapping[lowered]
    
    # If it looks like a full name (e.g. "French"), just title() it
    if len(lowered) > 3 and lowered.isalpha():
        return lowered.title()
    
    return lowered # Return as is (could be "fr", "ja", etc.)


def language_for_prompt(code: Optional[str], default: str = "Vietnamese") -> str:
    """
    Convert a language code/name into a prompt-friendly descriptor.
    """
    return normalize_language_code(code, default=default)

