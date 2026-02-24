"""
Phase 14.0: Predictive Pipeline Fusion (PPF)

A lightweight statistical classifier that predicts routing decisions
WITHOUT calling the LLM. Uses k-Nearest-Neighbors on historical
(query_features, decision) pairs to bypass the router for routine queries.

Self-learning: Every successful routing decision is recorded.
Zero hardcoding: All intelligence is derived from data patterns.
"""
import json
import math
import time
from pathlib import Path
from typing import Optional
from collections import Counter

import numpy as np

from utils.logger import get_logger

logger = get_logger()

# Routing decisions the PPF can predict
DECISIONS = ["CHAT", "PLAN", "NONE"]


class PPFClassifier:
    """
    Predictive Pipeline Fusion — k-NN classifier for routing bypass.
    
    Flow:
    1. Extract lightweight features from the user query.
    2. Compare against historical decision records using k-NN.
    3. If k neighbors strongly agree (≥ confidence_threshold), return the prediction.
    4. Otherwise, return None (fallback to full LLM router).
    """
    
    def __init__(
        self, 
        k: int = 5, 
        confidence_threshold: float = 0.85,
        history_file: str = None,
        max_history: int = 500
    ):
        self.k = k
        self.confidence_threshold = confidence_threshold
        self.max_history = max_history
        
        # Persistent storage path
        if history_file is None:
            history_file = str(Path(__file__).parent.parent.parent.parent / "data" / "ppf_history.json")
        self.history_file = history_file
        
        # In-memory history: list of {"features": [...], "decision": "CHAT|PLAN|NONE", "timestamp": float}
        self._history: list[dict] = []
        self._load_history()
    
    # ========================================
    # PUBLIC API
    # ========================================
    
    def predict(self, features: np.ndarray) -> tuple[Optional[str], float]:
        """
        Predict routing decision using k-NN voting.
        
        Args:
            features: Feature vector extracted from the query.
            
        Returns:
            (decision, confidence) or (None, 0.0) if not confident enough.
        """
        if len(self._history) < self.k:
            logger.info(f"[PPF] Insufficient history ({len(self._history)}/{self.k}). Skipping prediction.")
            return None, 0.0
        
        # Compute distances to all historical points
        distances = []
        for record in self._history:
            hist_features = np.array(record["features"], dtype=np.float32)
            dist = self._euclidean_distance(features, hist_features)
            distances.append((dist, record["decision"]))
        
        # Sort by distance (ascending) and take k nearest
        distances.sort(key=lambda x: x[0])
        k_nearest = distances[:self.k]
        
        # Vote: count decisions among k neighbors
        votes = Counter(d[1] for d in k_nearest)
        winner, winner_count = votes.most_common(1)[0]
        confidence = winner_count / self.k
        
        # Average distance of the k-nearest (for diagnostics)
        avg_dist = sum(d[0] for d in k_nearest) / self.k
        
        if confidence >= self.confidence_threshold:
            logger.info(
                f"[PPF] Prediction: '{winner}' | Confidence: {confidence:.0%} "
                f"| k={self.k} | Avg Distance: {avg_dist:.4f}"
            )
            return winner, confidence
        else:
            logger.info(
                f"[PPF] Low confidence ({confidence:.0%} < {self.confidence_threshold:.0%}). "
                f"Falling back to LLM router. Top vote: '{winner}'"
            )
            return None, confidence
    
    def record(self, features: np.ndarray, decision: str):
        """
        Record a successful routing decision for future learning.
        Called after every completed interaction.
        
        Args:
            features: Feature vector of the query.
            decision: The routing decision that was actually used (CHAT/PLAN/NONE).
        """
        if decision not in DECISIONS:
            logger.warning(f"[PPF] Unknown decision '{decision}', skipping record.")
            return
            
        record = {
            "features": features.tolist(),
            "decision": decision,
            "timestamp": time.time()
        }
        self._history.append(record)
        
        # Enforce max history (FIFO eviction)
        if len(self._history) > self.max_history:
            self._history = self._history[-self.max_history:]
        
        self._save_history()
        logger.info(f"[PPF] Recorded decision '{decision}'. History size: {len(self._history)}")
    
    # ========================================
    # FEATURE EXTRACTION
    # ========================================
    
    @staticmethod
    def extract_features(
        user_message: str, 
        query_vector: Optional[list[float]] = None
    ) -> np.ndarray:
        """
        Extract lightweight features from a user query.
        All features are dynamically derived — zero hardcoding.
        
        Features (18 total):
        [0]  word_count (normalized)
        [1]  has_question_mark
        [2]  avg_word_length (normalized)
        [3]  char_count (normalized)
        [4]  punctuation_ratio
        [5]  digit_ratio
        [6]  uppercase_ratio
        [7]  unique_word_ratio
        [8]  is_vietnamese (0/1)
        [9]  is_greeting (0/1)
        [10] is_command (0/1)
        [11] has_data_keywords (0/1)
        [12] message_complexity (0-1)
        [13] has_url (0/1)
        [14-17] query_vector_summary (mean, std, min, max)
        """
        msg = user_message.strip()
        words = msg.split()
        word_count = len(words)
        char_count = len(msg)
        
        # Basic text features
        f_word_count = min(word_count / 50.0, 1.0)
        f_has_question = 1.0 if "?" in msg else 0.0
        f_avg_word_len = min(sum(len(w) for w in words) / max(word_count, 1) / 15.0, 1.0)
        f_char_count = min(char_count / 200.0, 1.0)
        
        # Punctuation ratio
        punctuation_chars = sum(1 for c in msg if not c.isalnum() and not c.isspace())
        f_punct_ratio = punctuation_chars / max(char_count, 1)
        
        # Digit ratio
        digit_chars = sum(1 for c in msg if c.isdigit())
        f_digit_ratio = digit_chars / max(char_count, 1)
        
        # Uppercase ratio
        upper_chars = sum(1 for c in msg if c.isupper())
        f_upper_ratio = upper_chars / max(char_count, 1)
        
        # Unique word ratio (lexical diversity)
        unique_words = len(set(w.lower() for w in words))
        f_unique_ratio = unique_words / max(word_count, 1)
        
        # === New features (Phase C: InputPipeline-derived) ===
        msg_lower = msg.lower()
        
        # Vietnamese detection
        import re
        viet_chars = len(re.findall(r"[àáạảãâầấậẩẫăằắặẳẵèéẹẻẽêềếệểễìíịỉĩòóọỏõôồốộổỗơờớợởỡùúụủũưừứựửữỳýỵỷỹđ]", msg_lower))
        f_is_viet = 1.0 if viet_chars > 1 else 0.0
        
        # Greeting detection
        greeting_pats = ("hi", "hello", "hey", "chào", "xin chào", "yo", "good morning")
        f_is_greeting = 1.0 if any(msg_lower.startswith(g) for g in greeting_pats) and word_count < 6 else 0.0
        
        # Command detection
        cmd_pats = ("show", "list", "get", "find", "create", "delete", "update", "run", "check", "reset")
        first_word = words[0].lower() if words else ""
        f_is_command = 1.0 if first_word in cmd_pats else 0.0
        
        # Data keyword detection
        data_kw = {"database", "table", "query", "sql", "row", "column", "count",
                   "select", "track", "artist", "album", "user", "data"}
        f_has_data = 1.0 if any(k in msg_lower for k in data_kw) else 0.0
        
        # Message complexity (combination of length, diversity, punctuation)
        f_complexity = min((f_word_count * 0.3 + f_unique_ratio * 0.3 + f_punct_ratio * 0.2 + f_char_count * 0.2), 1.0)
        
        # URL presence
        f_has_url = 1.0 if "http" in msg_lower or "www." in msg_lower else 0.0
        
        features = [
            f_word_count,
            f_has_question,
            f_avg_word_len,
            f_char_count,
            f_punct_ratio,
            f_digit_ratio,
            f_upper_ratio,
            f_unique_ratio,
            f_is_viet,
            f_is_greeting,
            f_is_command,
            f_has_data,
            f_complexity,
            f_has_url,
        ]
        
        # Embedding summary (4 statistical features from the high-dimensional vector)
        if query_vector and len(query_vector) > 0:
            vec = np.array(query_vector, dtype=np.float32)
            features.extend([
                float(np.mean(vec)),
                float(np.std(vec)),
                float(np.min(vec)),
                float(np.max(vec)),
            ])
        else:
            features.extend([0.0, 0.0, 0.0, 0.0])
        
        return np.array(features, dtype=np.float32)

    
    # ========================================
    # INTERNAL
    # ========================================
    
    @staticmethod
    def _euclidean_distance(a: np.ndarray, b: np.ndarray) -> float:
        """Fast Euclidean distance between two feature vectors."""
        # Handle dimension mismatch gracefully
        min_len = min(len(a), len(b))
        return float(np.sqrt(np.sum((a[:min_len] - b[:min_len]) ** 2)))
    
    def _load_history(self):
        """Load historical decisions from disk."""
        try:
            path = Path(self.history_file)
            if path.exists():
                if path.stat().st_size == 0:
                    logger.debug("[PPF] History file is empty. Starting fresh.")
                    self._history = []
                    return
                with open(path, "r", encoding="utf-8") as f:
                    self._history = json.load(f)
                logger.debug(f"[PPF] Loaded {len(self._history)} historical decisions from disk.")
            else:
                logger.debug("[PPF] No history file found. Starting fresh (cold start).")
        except Exception as e:
            logger.warning(f"[PPF] Failed to load history: {e}. Starting fresh.")
            self._history = []
    
    def _save_history(self):
        """Persist history to disk."""
        try:
            path = Path(self.history_file)
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self._history, f)
        except Exception as e:
            logger.warning(f"[PPF] Failed to save history: {e}")
    
    def get_stats(self) -> dict:
        """Get classifier statistics for diagnostics."""
        if not self._history:
            return {"history_size": 0, "status": "cold_start"}
        
        decisions = Counter(r["decision"] for r in self._history)
        return {
            "history_size": len(self._history),
            "k": self.k,
            "confidence_threshold": self.confidence_threshold,
            "decision_distribution": dict(decisions),
            "status": "ready" if len(self._history) >= self.k else "warming_up"
        }


# ========================================
# SINGLETON
# ========================================
_ppf_instance: Optional[PPFClassifier] = None

def get_ppf_classifier() -> PPFClassifier:
    """Get or create the global PPF classifier instance."""
    global _ppf_instance
    if _ppf_instance is None:
        _ppf_instance = PPFClassifier()
    return _ppf_instance
