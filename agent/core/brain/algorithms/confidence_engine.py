"""
Phase 14.1: Adaptive Confidence Router (ACR)

Multi-signal confidence scoring engine that fuses 3 independent signals
using a weighted geometric mean to decide routing with calibrated certainty.

Signals:
  S1: Semantic Intent Match (cosine similarity to known intent archetypes)
  S2: PPF Classifier Score (from Phase 14.0)
  S3: History Pattern Match (Levenshtein similarity to recent successful queries)

Confidence = (S1^w1 * S2^w2 * S3^w3) ^ (1 / (w1+w2+w3))
"""
import math
import time
from typing import Optional
from collections import deque

import numpy as np

from utils.logger import get_logger

logger = get_logger()


class ConfidenceEngine:
    """
    Adaptive Confidence Router — Multi-Signal Fusion.
    
    Tiered decision making:
      Confidence ≥ 0.80 → Auto-route (zero LLM calls)
      Confidence ≥ 0.50 → Brief LLM confirmation (lightweight prompt)
      Confidence <  0.50 → Full LLM reasoning (current behavior)
    """
    
    # Signal weights (initialized equally, adaptable)
    DEFAULT_WEIGHTS = {
        "semantic": 1.0,  # S1: Intent registry match
        "ppf": 1.2,       # S2: PPF classifier (slightly higher — it has learning)
        "history": 0.8,   # S3: Recent query similarity
    }
    
    # Confidence tiers
    TIER_AUTO = 0.80    # Skip LLM entirely
    TIER_BRIEF = 0.50   # Use lightweight LLM prompt
    # Below 0.50 → Full LLM reasoning
    
    def __init__(self, max_recent: int = 50):
        self.weights = dict(self.DEFAULT_WEIGHTS)
        self._recent_queries: deque[dict] = deque(maxlen=max_recent)
        self._accuracy_log: list[dict] = []  # For dynamic weight adaptation
    
    def compute_confidence(
        self,
        user_message: str,
        query_vector: Optional[list[float]],
        ppf_confidence: float,
        ppf_decision: Optional[str],
        intent_match: Optional[str] = None,
        intent_similarity: float = 0.0,
        heuristic_score: float = 0.0,
    ) -> dict:
        """
        Compute multi-signal confidence for routing.
        
        Returns:
            {
                "tier": "auto" | "brief" | "full",
                "confidence": float,
                "predicted_decision": str | None,
                "signals": {"semantic": float, "ppf": float, "history": float, "heuristic": float}
            }
        """
        signals = {}
        
        # --- S1: Semantic Intent Match ---
        if intent_match and intent_similarity > 0:
            signals["semantic"] = min(intent_similarity, 1.0)
        else:
            signals["semantic"] = 0.0
        
        # --- S2: PPF Classifier ---
        signals["ppf"] = ppf_confidence if ppf_decision else 0.0
        
        # --- S3: History Pattern Match ---
        signals["history"] = self._compute_history_signal(user_message)
        
        # --- S4: Heuristic/Rule-based Signal ---
        signals["heuristic"] = heuristic_score
        
        # --- Fusion: Weighted Geometric Mean ---
        confidence = self._weighted_geometric_mean(signals)
        
        # --- Determine Tier ---
        if confidence >= self.TIER_AUTO:
            tier = "auto"
        elif confidence >= self.TIER_BRIEF:
            tier = "brief"
        else:
            tier = "full"
        
        # Determine predicted decision (vote across signals)
        predicted = ppf_decision or intent_match
        
        result = {
            "tier": tier,
            "confidence": confidence,
            "predicted_decision": predicted,
            "signals": signals,
        }
        
        # Log signals compactly
        sig_str = ", ".join([f"{k[0].upper()}={v:.2f}" for k, v in signals.items() if v > 0.05])
        if not sig_str: sig_str = "All=0.00"
        
        logger.info(
            f"[ACR] Confidence: {confidence:.2f} | Tier: {tier.upper()} | Signals: {sig_str}"
        )
        
        return result
    
    def record_query(self, user_message: str, decision: str, was_correct: bool = True):
        """Record a completed query for history matching and weight adaptation."""
        self._recent_queries.append({
            "message": user_message,
            "decision": decision,
            "timestamp": time.time(),
        })
        
        self._accuracy_log.append({
            "correct": was_correct,
            "timestamp": time.time(),
        })
        
        # Periodically adapt weights based on accuracy
        if len(self._accuracy_log) >= 20:
            self._adapt_weights()
    
    # ========================================
    # INTERNAL
    # ========================================
    
    def _compute_history_signal(self, user_message: str) -> float:
        """
        Compute similarity to the most similar recent query.
        Uses character-level Levenshtein ratio (fast, no external deps).
        """
        if not self._recent_queries:
            return 0.0
        
        best_ratio = 0.0
        msg_lower = user_message.lower().strip()
        
        for record in self._recent_queries:
            past_msg = record["message"].lower().strip()
            ratio = self._similarity_ratio(msg_lower, past_msg)
            if ratio > best_ratio:
                best_ratio = ratio
        
        return best_ratio
    
    @staticmethod
    def _similarity_ratio(a: str, b: str) -> float:
        """
        Fast string similarity using longest common subsequence ratio.
        Returns a value between 0.0 (completely different) and 1.0 (identical).
        """
        if a == b:
            return 1.0
        if not a or not b:
            return 0.0
        
        # Length-based quick rejection
        len_ratio = min(len(a), len(b)) / max(len(a), len(b))
        if len_ratio < 0.3:
            return 0.0
        
        # Token overlap ratio (fast approximation)
        tokens_a = set(a.split())
        tokens_b = set(b.split())
        if not tokens_a or not tokens_b:
            return 0.0
        
        intersection = tokens_a & tokens_b
        union = tokens_a | tokens_b
        return len(intersection) / len(union)  # Jaccard similarity
    
    def _weighted_geometric_mean(self, signals: dict) -> float:
        """
        Compute weighted geometric mean of ACTIVE signals only.
        
        Formula: (S1^w1 * S2^w2 * ...) ^ (1 / (w1+w2+...))
        
        Key fix (Phase 15.2): Zero signals are EXCLUDED from calculation
        instead of using epsilon. This prevents a single inactive signal
        (e.g. no history for new queries) from killing overall confidence.
        """
        epsilon = 0.05  # Signals below this are considered inactive
        total_weight = 0.0
        log_sum = 0.0
        active_count = 0
        
        for signal_name, value in signals.items():
            weight = self.weights.get(signal_name, 1.0)
            
            if value >= epsilon:
                # Signal is active — include in geometric mean
                log_sum += weight * math.log(value)
                total_weight += weight
                active_count += 1
        
        if total_weight == 0 or active_count == 0:
            return 0.0
        
        # Phase 21.0: Smarter coverage factor.
        # Don't penalize too hard if only one signal is active (common for new queries).
        # We use a non-linear scaling: 1 signal -> 0.7x, 2 -> 0.9x, 3+ -> 1.0x
        coverage_map = {1: 0.70, 2: 0.90, 3: 1.0, 4: 1.0}
        coverage_factor = coverage_map.get(active_count, 1.0)
        
        raw = math.exp(log_sum / total_weight)
        
        return raw * coverage_factor
    
    def _adapt_weights(self):
        """
        Self-tuning: Adjust signal weights based on recent accuracy.
        If accuracy is high, slightly increase PPF weight (it's learning well).
        If accuracy is low, decrease PPF weight and increase semantic weight.
        """
        recent = self._accuracy_log[-20:]
        accuracy = sum(1 for r in recent if r["correct"]) / len(recent)
        
        if accuracy >= 0.9:
            # PPF is performing well, trust it more
            self.weights["ppf"] = min(self.weights["ppf"] * 1.05, 2.0)
            logger.info(f"[ACR] Accuracy {accuracy:.0%}. Boosting PPF weight → {self.weights['ppf']:.2f}")
        elif accuracy < 0.7:
            # PPF is struggling, rely more on semantic
            self.weights["ppf"] = max(self.weights["ppf"] * 0.90, 0.5)
            self.weights["semantic"] = min(self.weights["semantic"] * 1.05, 2.0)
            logger.info(f"[ACR] Accuracy {accuracy:.0%}. Reducing PPF weight → {self.weights['ppf']:.2f}")
        
        # Clear log after adaptation
        self._accuracy_log = []


# ========================================
# SINGLETON
# ========================================
_instance: Optional[ConfidenceEngine] = None

def get_confidence_engine() -> ConfidenceEngine:
    global _instance
    if _instance is None:
        _instance = ConfidenceEngine()
    return _instance
