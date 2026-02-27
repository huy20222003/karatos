"""
Language Utility
Provides normalization and prompt-friendly formatting for language signals.
"""

from __future__ import annotations

from typing import Optional


def normalize_language_code(code: Optional[str], default: str = "en") -> str:
    """
    Normalize a language code coming from InputPipeline/LLM/user settings.

    - Accepts ISO-639-1 codes (e.g., "vi", "en") and common BCP-47 forms
      (e.g., "pt-BR", "zh-Hans"), returning a lowercased version.
    - Normalizes "mixed" to "vi" to avoid producing an invalid language target.
    - Falls back to `default` when missing or invalid.
    """
    if not code:
        return default

    raw = str(code).strip()
    if not raw:
        return default

    lowered = raw.lower()
    if lowered == "mixed":
        return "vi"

    # Very small validation: allow alpha + hyphen (BCP-47-like).
    for ch in lowered:
        if not (ch.isalpha() or ch == "-"):
            return default

    # Require at least 2 letters to be meaningful.
    letters = [c for c in lowered if c.isalpha()]
    if len(letters) < 2:
        return default

    return lowered


def language_for_prompt(code: Optional[str], default: str = "en") -> str:
    """
    Convert a language code into a prompt-friendly descriptor.

    For known common codes we provide an explicit name; otherwise we provide
    a generic "Language code: <code>" hint that is not limited to vi/en.
    """
    norm = normalize_language_code(code, default=default)
    if norm == "vi":
        return "Vietnamese"
    if norm == "en":
        return "English"
    return f"Language code: {norm}"

