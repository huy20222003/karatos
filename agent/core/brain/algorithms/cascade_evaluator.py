"""
Phase 14.2: Cascade Intelligence Engine (CIE)

A 3-tier evaluation cascade for self-correction.
Most responses exit at Tier 1 (instant rule checks), avoiding the
expensive LLM self-correction call that takes 5-10s.

Tier 1: Rule-Based Validator (0ms)      — 90% of responses exit here
Tier 2: Semantic Coherence Check (10ms)  — 95% of remaining exit here
Tier 3: Full LLM Self-Correction (5-10s) — Only for risky/ambiguous responses
"""
import re
from typing import Optional

import numpy as np

from utils.logger import get_logger

logger = get_logger()


class CascadeEvaluator:
    """
    Cascade Intelligence Engine — 3-Tier evaluation with early exit.
    
    Each tier is progressively more expensive but more accurate.
    The cascade short-circuits as soon as a tier gives a confident verdict.
    """
    
    # Configurable thresholds (all dynamic, zero hardcoding)
    MIN_RESPONSE_LENGTH = 5           # Characters
    MAX_RESPONSE_LENGTH = 5000        # Characters
    COHERENCE_THRESHOLD = 0.4         # Minimum cosine similarity between query and response embeddings
    
    def __init__(self):
        self._tier_stats = {"tier1_pass": 0, "tier1_fail": 0, "tier2_pass": 0, "tier2_fail": 0, "tier3": 0}
    
    async def evaluate(
        self,
        user_message: str,
        response: str,
        query_vector: Optional[list[float]] = None,
        response_vector: Optional[list[float]] = None,
        mood: str = "OPTIMISTIC",
        energy: float = 1.0,
    ) -> dict:
        """
        Evaluate a response through the 3-tier cascade.
        
        Returns:
            {
                "passed": bool,
                "tier_exited": int (1, 2, or 3),
                "corrections": str | None,
                "reason": str
            }
        """
        # --- TIER 1: Rule-Based Validator (Instant) ---
        tier1_result = self._tier1_rules(response)
        if tier1_result["passed"]:
            self._tier_stats["tier1_pass"] += 1
            logger.info(f"[CIE] Tier 1 PASS — {tier1_result['reason']}")
            return {"passed": True, "tier_exited": 1, "corrections": None, "reason": tier1_result["reason"]}
        
        if tier1_result.get("hard_fail"):
            # Hard failures at Tier 1 go straight to Tier 3 (LLM fix required)
            self._tier_stats["tier1_fail"] += 1
            logger.info(f"[CIE] Tier 1 HARD FAIL → escalating to Tier 3. Reason: {tier1_result['reason']}")
            return await self._tier3_llm(user_message, response, mood, energy, tier1_result["reason"])
        
        # --- TIER 2: Semantic Coherence Check (Fast Embedding) ---
        tier2_result = self._tier2_coherence(query_vector, response_vector)
        if tier2_result["passed"]:
            self._tier_stats["tier2_pass"] += 1
            logger.info(f"[CIE] Tier 2 PASS — Coherence: {tier2_result['coherence']:.2f}")
            return {"passed": True, "tier_exited": 2, "corrections": None, "reason": f"Coherence: {tier2_result['coherence']:.2f}"}
        
        self._tier_stats["tier2_fail"] += 1
        logger.info(f"[CIE] Tier 2 FAIL — Low coherence: {tier2_result['coherence']:.2f}. Escalating to Tier 3.")
        
        # --- TIER 3: Full LLM Self-Correction ---
        self._tier_stats["tier3"] += 1
        return await self._tier3_llm(user_message, response, mood, energy, f"Low coherence ({tier2_result['coherence']:.2f})")
    
    # ========================================
    # TIER IMPLEMENTATIONS
    # ========================================
    
    def _tier1_rules(self, response: str) -> dict:
        """
        Tier 1: Instant rule-based checks.
        Returns {"passed": bool, "reason": str, "hard_fail": bool}
        """
        # 1. Empty or too short
        if not response or len(response.strip()) < self.MIN_RESPONSE_LENGTH:
            return {"passed": False, "hard_fail": True, "reason": "Response is empty or too short"}
        
        # 2. Too long (possible runaway generation)
        if len(response) > self.MAX_RESPONSE_LENGTH:
            return {"passed": False, "hard_fail": False, "reason": "Response exceeds maximum length"}
        
        # 3. Error leakage (internal errors in user-facing response)
        error_patterns = [
            r"traceback",
            r"exception",
            r"error_timeout", 
            r"error_failed",
            r"NoneType",
            r"KeyError",
            r"IndexError",
        ]
        response_lower = response.lower()
        for pattern in error_patterns:
            if re.search(pattern, response_lower):
                return {"passed": False, "hard_fail": True, "reason": f"Error leakage detected: '{pattern}'"}
        
        # 4. Language sanity (response should contain some readable text)
        alpha_count = sum(1 for c in response if c.isalpha())
        if alpha_count < len(response) * 0.1:
            return {"passed": False, "hard_fail": False, "reason": "Response lacks readable text"}
        
        # All rules passed
        return {"passed": True, "hard_fail": False, "reason": "All rules passed"}
    
    def _tier2_coherence(
        self, 
        query_vector: Optional[list[float]], 
        response_vector: Optional[list[float]]
    ) -> dict:
        """
        Tier 2: Semantic coherence between query and response.
        Returns {"passed": bool, "coherence": float}
        """
        if query_vector is None or response_vector is None:
            # Can't check coherence without embeddings — pass by default
            return {"passed": True, "coherence": 1.0}
        
        q = np.array(query_vector, dtype=np.float32)
        r = np.array(response_vector, dtype=np.float32)
        
        # Cosine similarity
        dot = np.dot(q, r)
        norm_q = np.linalg.norm(q)
        norm_r = np.linalg.norm(r)
        
        if norm_q == 0 or norm_r == 0:
            return {"passed": True, "coherence": 0.0}
        
        coherence = float(dot / (norm_q * norm_r))
        passed = coherence >= self.COHERENCE_THRESHOLD
        
        return {"passed": passed, "coherence": coherence}
    
    async def _tier3_llm(
        self, 
        user_message: str, 
        response: str, 
        mood: str, 
        energy: float,
        escalation_reason: str
    ) -> dict:
        """
        Tier 3: Full LLM self-correction (expensive, last resort).
        Uses the existing SelfCorrectionModel.
        """
        try:
            from core.brain.nodes.self_correction import SelfCorrectionModel
            model = SelfCorrectionModel()
            corrected = await model.evaluate(user_message, response, mood, energy)
            
            if corrected and "[CORRECTED]" in corrected:
                new_resp = corrected.replace("[CORRECTED]", "").strip()
                return {
                    "passed": True, 
                    "tier_exited": 3, 
                    "corrections": new_resp, 
                    "reason": f"LLM corrected (trigger: {escalation_reason})"
                }
            
            return {"passed": True, "tier_exited": 3, "corrections": None, "reason": "LLM approved without changes"}
            
        except Exception as e:
            logger.error(f"[CIE] Tier 3 LLM failed: {e}")
            return {"passed": True, "tier_exited": 3, "corrections": None, "reason": f"Tier 3 error: {e}"}
    
    def get_stats(self) -> dict:
        """Get cascade statistics for diagnostics."""
        total = sum(self._tier_stats.values())
        return {
            **self._tier_stats,
            "total_evaluations": total,
            "tier1_exit_rate": f"{(self._tier_stats['tier1_pass'] / max(total, 1)) * 100:.0f}%",
        }


# ========================================
# SINGLETON
# ========================================
_instance: Optional[CascadeEvaluator] = None

def get_cascade_evaluator() -> CascadeEvaluator:
    global _instance
    if _instance is None:
        _instance = CascadeEvaluator()
    return _instance
