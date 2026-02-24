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
from typing import List, Optional

from utils.logger import get_logger

logger = get_logger()

# ── Pre-compiled patterns ─────────────────────────────────────

_RE_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_RE_ZWSP = re.compile(r"[\u200b\u200c\u200d\ufeff\u2060]")
_RE_MULTI_SPACE = re.compile(r"\s{3,}")

# Question signals (vi + en)
_Q_SIGNALS_EN = re.compile(
    r"(?i)\b(what|how|where|when|who|why|which|can you|could you|is there|are there)\b"
)
_Q_SIGNALS_VI = re.compile(
    r"(?i)(là gì|ở đâu|khi nào|tại sao|như thế nào|có ai|ai biết|giúp|bao nhiêu)"
)

# Command signals
_CMD_SIGNALS = re.compile(
    r"(?i)^(show|list|get|find|create|delete|update|run|start|stop|set|check|reset|deploy)\b"
)

# Data / query signals
_DATA_SIGNALS = re.compile(
    r"(?i)\b(database|table|query|sql|row|column|count|select|track|artist|album|user)\b"
)

# Greeting signals
_GREETING_SIGNALS = re.compile(
    r"(?i)^(hi|hello|hey|chào|xin chào|yo|good morning|good afternoon)\b"
)

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

    def process(self, text: str, *,
                source: str = "unknown",
                sender: str = "unknown",
                chat_id: str = "") -> ProcessedInput:
        """Run the full pipeline: sanitize → fingerprint → classify → enrich."""

        # 1) SANITIZE
        clean = self._sanitize(text)

        # 2) FINGERPRINT (single pass over clean text)
        fp = self._fingerprint(clean)

        # 3) CLASSIFY content type
        content_type = self._classify(clean, fp)

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
        if not text:
            return ""
        # Unicode NFC normalization
        text = unicodedata.normalize("NFC", text)
        # Strip control characters (keep \n \r \t)
        text = _RE_CONTROL.sub("", text)
        # Remove zero-width characters (used for injection bypass)
        text = _RE_ZWSP.sub("", text)
        # Collapse excessive whitespace
        text = _RE_MULTI_SPACE.sub("  ", text)
        return text.strip()

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

    @staticmethod
    def _classify(text: str, fp: dict) -> str:
        """Lightweight content type classification (no LLM)."""
        if _GREETING_SIGNALS.search(text) and fp["word_count"] < 6:
            return "social"
        if _CMD_SIGNALS.search(text):
            return "command"
        if _DATA_SIGNALS.search(text) and fp["word_count"] >= 3:
            return "data"
        if fp.get("has_question"):
            return "question"
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
