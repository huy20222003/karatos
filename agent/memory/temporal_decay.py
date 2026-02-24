"""
Phase 14.3: Temporal Decay Memory (TDM)

Exponential temporal decay with frequency boost for Experience Memory.
Fresh, frequently-used patterns get priority. Ancient, rarely-used ones fade.

Freshness(m) = base_score * e^(-λ * age_hours) * (1 + log(recall_count + 1))
"""
import math
import time
from typing import Optional

from utils.logger import get_logger

logger = get_logger()


class TemporalDecayScorer:
    """
    Scores experience memory entries using temporal decay + frequency boost.
    
    A memory that was recalled 5 minutes ago and recalled 10 times 
    will score much higher than one from 30 days ago recalled once.
    """
    
    def __init__(self, decay_rate: float = 0.01, min_score: float = 0.01):
        """
        Args:
            decay_rate: λ in the decay formula. Higher = faster decay.
                        0.01 → half-life ~69 hours (smooth decay)
                        0.05 → half-life ~14 hours (aggressive decay)
            min_score: Floor score to prevent entries from reaching zero.
        """
        self.decay_rate = decay_rate
        self.min_score = min_score
    
    def score(
        self, 
        similarity: float,
        created_at: Optional[float] = None,
        last_recalled_at: Optional[float] = None,
        recall_count: int = 0,
    ) -> float:
        """
        Compute composite score: similarity * freshness * frequency_boost.
        
        Args:
            similarity: Base similarity score (e.g., 1 - cosine_distance). Range [0, 1].
            created_at: Unix timestamp when the memory was created.
            last_recalled_at: Unix timestamp of the last successful recall. 
                              Falls back to created_at if never recalled.
            recall_count: Number of times this memory was successfully recalled.
            
        Returns:
            Composite score. Higher is better.
        """
        now = time.time()
        
        # Determine the "age anchor" (last recall or creation time)
        anchor = last_recalled_at or created_at or now
        age_hours = max((now - anchor) / 3600.0, 0.0)
        
        # Exponential decay
        decay_factor = math.exp(-self.decay_rate * age_hours)
        
        # Frequency boost: log scale so diminishing returns
        frequency_boost = 1.0 + math.log(recall_count + 1)
        
        # Composite score
        raw_score = similarity * decay_factor * frequency_boost
        final_score = max(raw_score, self.min_score)
        
        logger.debug(
            f"[TDM] Score: {final_score:.4f} "
            f"(sim={similarity:.3f}, decay={decay_factor:.3f}, "
            f"freq_boost={frequency_boost:.2f}, age={age_hours:.1f}h)"
        )
        
        return final_score
    
    def boost(self, memory_meta: dict) -> dict:
        """
        Boost a memory entry after successful recall.
        Updates recall_count and last_recalled_at.
        
        Args:
            memory_meta: The memory's metadata dict (mutated in place).
            
        Returns:
            Updated metadata dict.
        """
        memory_meta["recall_count"] = memory_meta.get("recall_count", 0) + 1
        memory_meta["last_recalled_at"] = time.time()
        logger.info(
            f"[TDM] Memory boosted. recall_count={memory_meta['recall_count']}, "
            f"last_recalled_at={memory_meta['last_recalled_at']:.0f}"
        )
        return memory_meta
    
    def get_half_life_hours(self) -> float:
        """Calculate the half-life in hours for the current decay rate."""
        if self.decay_rate <= 0:
            return float('inf')
        return math.log(2) / self.decay_rate


# ========================================
# SINGLETON
# ========================================
_instance: Optional[TemporalDecayScorer] = None

def get_temporal_decay_scorer() -> TemporalDecayScorer:
    global _instance
    if _instance is None:
        _instance = TemporalDecayScorer()
    return _instance
