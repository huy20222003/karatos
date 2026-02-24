"""
InputPipeline — Single-pass input preprocessing.

Runs BEFORE the brain receives any message:
  SANITIZE → FINGERPRINT → CLASSIFY → ENRICH

Produces a ProcessedInput with all enrichments attached.
Zero LLM calls. Pure algorithmic. O(n) per message.
"""
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Any
from utils.helpers import task_timer

from utils.logger import get_logger

logger = get_logger()

# ── Pre-compiled patterns ─────────────────────────────────────

_RE_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_RE_ZWSP = re.compile(r"[\u200b\u200c\u200d\ufeff\u2060]")
_RE_MULTI_SPACE = re.compile(r"\s{3,}")

# --- Centralized Heuristic Signals (Placeholder) ---
# These are loaded from heuristics.yaml at runtime
_SIGNAL_CACHE = None

def _get_signals():
    global _SIGNAL_CACHE
    if _SIGNAL_CACHE is None:
        try:
            from core.brain.prompts.registry import get_prompt_registry
            registry = get_prompt_registry()
            # In a real scenario, we might add a 'get_raw' or similar to registry
            # For now, we'll use a simplified loading logic
            import yaml
            import os
            h_path = os.path.join(os.path.dirname(__file__), "..", "prompts", "system", "heuristics.yaml")
            with open(h_path, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)
                _SIGNAL_CACHE = data.get("signals", {})
        except Exception:
            _SIGNAL_CACHE = {}
    return _SIGNAL_CACHE

# Vietnamese character range heuristic
_RE_VIET = re.compile(r"[àáạảãâầấậẩẫăằắặẳẵèéẹẻẽêềếệểễìíịỉĩòóọỏõôồốộổỗơờớợởỡùúụủũưừứựửữỳýỵỷỹđ]")


@dataclass
class ProcessedInput:
    """Enriched input ready for the brain."""
    raw_text: str
    clean_text: str
    language: str             # 'vi' | 'en' | 'mixed'
    content_type: str         # 'question' | 'command' | 'social' | 'data' | 'general'
    token_estimate: int
    risk_score: float         # 0.0 – 1.0
    risk_flags: List[str] = field(default_factory=list)
    fingerprint: dict = field(default_factory=dict)
    metadata: dict = field(default_factory=dict)

    @property
    def is_safe(self) -> bool:
        return self.risk_score < 0.4


class InputPipeline:
    """
    Single-pass input processor.

    Usage:
        pipe = InputPipeline()
        processed = pipe.process(raw_text, source="telegram", sender="user123")
    """

    async def process(self, text: str, *,
                source: str = "unknown",
                sender: str = "unknown",
                chat_id: str = "") -> ProcessedInput:
        """Run the full pipeline: sanitize → fingerprint → classify → enrich."""

        # 1) SANITIZE
        clean = self._sanitize(text)

        # 2) FINGERPRINT (single pass over clean text)
        fp = self._fingerprint(clean)

        # 3) CLASSIFY content type (Brain-based)
        content_type = await self._classify(clean, fp)

        # 4) RISK assessment
        risk_score, risk_flags = self._assess_risk(clean)

        # 5) Build result
        result = ProcessedInput(
            raw_text=text,
            clean_text=clean,
            language=fp["language"],
            content_type=content_type,
            token_estimate=fp["token_estimate"],
            risk_score=risk_score,
            risk_flags=risk_flags,
            fingerprint=fp,
            metadata={
                "source": source,
                "sender": sender,
                "chat_id": chat_id,
                "processed_at": datetime.utcnow().isoformat(),
            },
        )

        logger.debug(
            f"[INPUT] lang={result.language} type={result.content_type} "
            f"tokens≈{result.token_estimate} risk={result.risk_score:.2f}"
        )
        return result

    # ── Stage 1: Sanitize ──────────────────────────────────────

    @staticmethod
    def _sanitize(text: str) -> str:
        """Unified sanitization via SecurityShield."""
        from utils.security import SecurityShield
        return SecurityShield.sanitize_text(text)

    # ── Stage 2: Fingerprint ───────────────────────────────────

    @staticmethod
    def _fingerprint(text: str) -> dict:
        """O(n) single-pass statistical analysis."""
        if not text:
            return {"word_count": 0, "char_count": 0, "token_estimate": 0,
                    "language": "en", "has_question": False,
                    "punct_ratio": 0.0, "digit_ratio": 0.0,
                    "upper_ratio": 0.0, "unique_ratio": 0.0}

        chars = len(text)
        words = text.split()
        wc = len(words)
        unique = len(set(w.lower() for w in words))

        upper = sum(1 for c in text if c.isupper())
        digits = sum(1 for c in text if c.isdigit())
        punct = sum(1 for c in text if not c.isalnum() and not c.isspace())

        # Language detection (heuristic)
        viet_chars = len(_RE_VIET.findall(text))
        if viet_chars > 2 or (viet_chars > 0 and viet_chars / max(wc, 1) > 0.15):
            lang = "vi"
        elif viet_chars > 0:
            lang = "mixed"
        else:
            lang = "en"

        # Token estimate (~1.3 tokens per word for English, ~1.5 for Vietnamese)
        token_mult = 1.5 if lang == "vi" else 1.3
        token_est = int(wc * token_mult)

        return {
            "word_count": wc,
            "char_count": chars,
            "token_estimate": token_est,
            "language": lang,
            "has_question": ("?" in text or bool(_Q_SIGNALS_EN.search(text)) or bool(_Q_SIGNALS_VI.search(text))),
            "punct_ratio": punct / max(chars, 1),
            "digit_ratio": digits / max(chars, 1),
            "upper_ratio": upper / max(chars, 1),
            "unique_ratio": unique / max(wc, 1),
            "avg_word_len": sum(len(w) for w in words) / max(wc, 1),
        }

    # ── Stage 3: Classify ──────────────────────────────────────

    async def _classify(self, text: str, fp: dict) -> str:
        """Brain-first content type classification with Centralized Heuristics."""
        if not text or fp["word_count"] == 0:
            return "general"

        # ── 1. CENTRALIZED REFLEX SIGNALS (Fast, Zero Latency) ──────────
        signals = _get_signals()
        
        # Social
        g_sig = signals.get("greeting", {}).get("pattern")
        if g_sig and re.search(g_sig, text) and fp["word_count"] < 4:
            return "social"

        # Command
        c_sig = signals.get("command", {}).get("pattern")
        if text.startswith("/") or (c_sig and re.search(c_sig, text) and fp["word_count"] < 8):
            return "command"

        # ── 2. BRAIN CLASSIFICATION (Main Logic) ──────────────────────────
        with task_timer("Neural Input Classification"):
            try:
                from .brain.model import BrainModel
                classifier = BrainModel(mode="classifier")
                content = await classifier.think(f"User Message: \"{text}\"", mood="NEUTRAL", timeout=60.0)
                
                if content:
                    valid_categories = {"question", "command", "social", "data", "general"}
                    for cat in valid_categories:
                        if cat in content.lower():
                            return cat
                
                return "general"
            except Exception as e:
                logger.warning(f"[INPUT_PIPELINE] Brain Classification failed: {e}. Falling back to internal heuristics.")
                # Final fallback via centralized signals
                d_sig = signals.get("data", {}).get("pattern")
                if d_sig and re.search(d_sig, text): return "data"
                
                q_sig = signals.get("question", {}).get("pattern")
                if q_sig and re.search(q_sig, text): return "question"
                
                return "general"

    # ── Stage 4: Risk Assessment ───────────────────────────────

    @staticmethod
    def _assess_risk(text: str) -> tuple:
        """Fast risk scoring using pre-compiled patterns."""
        score = 0.0
        flags = []

        from utils.security import SecurityShield

        # Prompt injection
        inj = SecurityShield.detect_prompt_injection(text)
        if not inj["safe"]:
            score += 0.4
            flags.append(inj.get("reason", "injection"))

        # Encoding tricks
        enc = SecurityShield.detect_suspicious_encoding(text)
        if not enc["safe"]:
            score += 0.2
            flags.append(enc.get("reason", "encoding"))

        # Secret leakage check
        leak = SecurityShield.detect_secret_leakage(text)
        if leak:
            score += 0.15
            flags.append("potential_secret_leak")

        # Excessive length (could be context stuffing attack)
        if len(text) > 5000:
            score += 0.1
            flags.append("excessive_length")

        return min(score, 1.0), flags
