"""
Phase 14.4: Neural Query Planner (NQP)

Recursive Query Decomposition for complex natural-language queries.
Breaks complex multi-entity requests into atomic sub-queries,
executes each independently, then merges results programmatically.

This avoids the LLM having to generate monster SQL with CTEs, subqueries,
and multiple aggregations in a single shot (high failure rate).
"""
import re
from typing import Optional

from utils.logger import get_logger

logger = get_logger()


class NeuralQueryPlanner:
    """
    Neural Query Planner — Complexity estimation and query decomposition.
    
    Flow:
    1. Estimate query complexity.
    2. If simple → return None (let normal pipeline handle it).
    3. If complex → decompose into sub-queries with merge instructions.
    """
    
    # Complexity threshold: above this, we decompose
    COMPLEXITY_THRESHOLD = 3.0
    
    # Complexity signals (all dynamically scored from the query text)
    # Each signal adds to the total complexity score
    ENTITY_KEYWORDS = {
        "user", "users", "người dùng", "tài khoản", "account",
        "track", "tracks", "song", "bài hát", "bản nhạc",
        "artist", "nghệ sĩ", "ca sĩ",
        "transaction", "giao dịch", "thanh toán", "payment", "vnpay",
        "playlist", "danh sách phát",
        "genre", "thể loại",
    }
    
    AGGREGATION_KEYWORDS = {
        "top", "most", "least", "nhiều nhất", "ít nhất", "trung bình",
        "average", "count", "total", "sum", "max", "min",
        "highest", "lowest", "cao nhất", "thấp nhất",
        "rank", "ranking", "xếp hạng",
    }
    
    TIME_KEYWORDS = {
        "today", "hôm nay", "yesterday", "hôm qua",
        "this month", "tháng này", "last month", "tháng trước",
        "this week", "tuần này", "last week", "tuần trước",
        "this year", "năm nay", "recent", "gần đây", "mới nhất",
    }
    
    CONDITION_KEYWORDS = {
        "where", "who", "which", "whose",
        "have", "has", "with", "without",
        "more than", "less than", "hơn", "dưới",
        "between", "giữa", "excluding", "except",
    }
    
    def estimate_complexity(self, user_input: str) -> dict:
        """
        Estimate query complexity by counting signals.
        
        Returns:
            {
                "score": float,
                "is_complex": bool,
                "signals": {"entities": int, "aggregations": int, "time_filters": int, "conditions": int}
            }
        """
        input_lower = user_input.lower()
        
        # Count distinct entities mentioned
        entities = sum(1 for kw in self.ENTITY_KEYWORDS if kw in input_lower)
        # Count aggregation operations
        aggregations = sum(1 for kw in self.AGGREGATION_KEYWORDS if kw in input_lower)
        # Count time filters
        time_filters = sum(1 for kw in self.TIME_KEYWORDS if kw in input_lower)
        # Count conditions
        conditions = sum(1 for kw in self.CONDITION_KEYWORDS if kw in input_lower)
        
        # Weighted complexity score
        score = (
            entities * 1.0 +        # Each entity adds 1.0
            aggregations * 1.5 +     # Aggregations are harder
            time_filters * 0.8 +     # Time filters add moderate complexity
            conditions * 0.5         # Conditions add some complexity
        )
        
        result = {
            "score": score,
            "is_complex": score >= self.COMPLEXITY_THRESHOLD,
            "signals": {
                "entities": entities,
                "aggregations": aggregations,
                "time_filters": time_filters,
                "conditions": conditions,
            }
        }
        
        logger.info(
            f"[NQP] Complexity: {score:.1f} "
            f"(E={entities}, A={aggregations}, T={time_filters}, C={conditions}) "
            f"→ {'COMPLEX' if result['is_complex'] else 'SIMPLE'}"
        )
        
        return result
    
    async def decompose(
        self, 
        user_input: str, 
        schema_context: str,
        tables: list[str],
    ) -> Optional[list[dict]]:
        """
        Decompose a complex query into atomic sub-queries using LLM.
        
        Returns:
            List of sub-query dicts: [
                {"sub_query": "...", "purpose": "...", "merge_key": "..."},
                ...
            ]
            Or None if decomposition fails.
        """
        try:
            from core.brain.model import SharedModelProvider
            model = SharedModelProvider.get_model()
            
            decomposition_prompt = (
                f"You are a SQL query planner. Break this complex request into 2-3 simpler sub-queries.\n\n"
                f"USER REQUEST: {user_input}\n\n"
                f"AVAILABLE TABLES: {', '.join(tables)}\n\n"
                f"SCHEMA:\n{schema_context[:2000]}\n\n"  # Cap schema to avoid overflow
                f"RULES:\n"
                f"1. Each sub-query should target ONE main entity/table.\n"
                f"2. Include a 'merge_key' — the column to JOIN results on.\n"
                f"3. Keep each sub-query simple (no subqueries or CTEs).\n"
                f"4. Return ONLY valid JSON array.\n\n"
                f"RESPONSE FORMAT:\n"
                f'[{{"sub_query": "natural language description", "purpose": "what this fetches", "merge_key": "column_name"}}]\n\n'
                f"RESPOND WITH JSON ONLY:"
            )
            
            import asyncio
            response = await asyncio.wait_for(model.ainvoke(decomposition_prompt), timeout=120.0)
            
            # Parse JSON from response
            from core.brain.utils import extract_json
            result = extract_json(response)
            
            if isinstance(result, list) and len(result) >= 2:
                logger.info(f"[NQP] Decomposed into {len(result)} sub-queries.")
                for i, sq in enumerate(result):
                    logger.info(f"  Sub-Q{i+1}: {sq.get('sub_query', '?')} (merge: {sq.get('merge_key', '?')})")
                return result
            else:
                logger.info("[NQP] Decomposition did not produce valid sub-queries. Falling back to single query.")
                return None
                
        except Exception as e:
            logger.warning(f"[NQP] Decomposition failed: {e}. Falling back to single query.")
            return None
    
    @staticmethod
    def merge_results(sub_results: list[list[dict]], merge_key: str) -> list[dict]:
        """
        Merge results from sub-queries using a common key.
        
        Args:
            sub_results: List of result sets (each is a list of row dicts).
            merge_key: Column name to JOIN on.
            
        Returns:
            Merged list of row dicts.
        """
        if not sub_results:
            return []
        
        if len(sub_results) == 1:
            return sub_results[0]
        
        # Build lookup from first result set
        base = sub_results[0]
        merged_lookup = {}
        for row in base:
            key_val = row.get(merge_key)
            if key_val is not None:
                merged_lookup[key_val] = dict(row)
        
        # Merge additional result sets
        for result_set in sub_results[1:]:
            for row in result_set:
                key_val = row.get(merge_key)
                if key_val is not None:
                    if key_val in merged_lookup:
                        # Merge columns (don't overwrite existing)
                        for col, val in row.items():
                            if col not in merged_lookup[key_val]:
                                merged_lookup[key_val][col] = val
                    else:
                        merged_lookup[key_val] = dict(row)
        
        merged = list(merged_lookup.values())
        logger.info(f"[NQP] Merged {len(sub_results)} result sets → {len(merged)} rows (key: {merge_key})")
        return merged


# ========================================
# SINGLETON
# ========================================
_instance: Optional[NeuralQueryPlanner] = None

def get_query_planner() -> NeuralQueryPlanner:
    global _instance
    if _instance is None:
        _instance = NeuralQueryPlanner()
    return _instance
