import json
import asyncio
from datetime import datetime
from typing import Optional, List, Dict, Any

from core.brain.model import BrainModel
from utils.logger import get_logger

logger = get_logger()

class MemoryDistiller(BrainModel):
    """
    The 'Digital Soul' Distiller.
    Analyzes raw interactions and distills them into atomic, categorized memory units.
    """
    def __init__(self):
        super().__init__(mode="DISTILLER")

    async def distill_interaction(self, user_text: str, agent_response: str) -> List[Dict[str, Any]]:
        """
        Analyze a chat interaction and extract atomic memory units.
        Returns a list of distilled facts/sentiments/reflections.
        """
        interaction_str = f"User: \"{user_text}\"\nAssistant: \"{agent_response}\""
        
        # --- NGO FIX: Explicit extraction command to break chat bias ---
        command = "EXTRACT MEMORY UNITS FROM THE ABOVE INTERACTION INTO A JSON LIST. RETURN ONLY JSON."
        
        try:
            # Note: BrainModel.think now passes interaction_str into {interaction_str} in distiller.yaml
            raw_response = await self.think(
                command, 
                phase="distiller", 
                interaction_str=interaction_str, 
                mood="ANALYTICAL", 
                timeout=180.0
            )
            
            if raw_response in ["ERROR_TIMEOUT", "ERROR_FAILED"]:
                logger.error(f"[DISTILLER] Brain think failed: {raw_response}")
                return []

            # Basic JSON cleanup (handling potential markdown fences)
            from core.brain.utils import extract_json
            units = extract_json(raw_response)
            
            if not units or not isinstance(units, list):
                return []
                
            return units
        except Exception as e:
            logger.error(f"[DISTILLER] Distillation failed: {e}")
            return []

    async def distill_reflection(self, task_description: str, outcome: str, errors: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Specially distills an autonomous task result into EXPERIENCE or REFLECTION.
        """
        # --- NGO FIX: Use Prompt Registry for Reflection ---
        from core.brain.prompts.registry import get_prompt_registry
        registry = get_prompt_registry()
        
        # We pass context directly to avoid identity injection conflicts if needed
        # but here we follow the standard get_system_prompt pattern
        prompt_content = f"EXTRACT EXPERIENCE MEMORY UNITS FROM THE FOLLOWING TASK:\nTask: {task_description}\nOutcome: {outcome}\nReturn ONLY JSON."
        
        try:
            logger.info(f"[DISTILLER] Distilling reflection for task: {task_description[:50]}...")
            
            # Using specific phase for reflection
            raw_response = await self.think(
                prompt_content, 
                phase="distiller_reflection", 
                task_description=task_description,
                outcome=outcome,
                errors=errors or "None",
                mood="ANALYTICAL", 
                timeout=180.0
            )
            
            if raw_response in ["ERROR_TIMEOUT", "ERROR_FAILED"]:
                return []

            from core.brain.utils import extract_json
            lessons = extract_json(raw_response)
            
            if lessons:
                logger.info(f"[DISTILLER] Extracted {len(lessons)} lessons.")
            return lessons or []
        except Exception as e:
            logger.error(f"[DISTILLER] Reflection distillation failed: {e}")
            return []

    async def reconcile_persona(self, memory_units: List[str]) -> Dict[str, Any]:
        """
        Neural Identity Reconciliation.
        Synthesizes multiple persona-related memory units into a coherent identity.
        """
        units_str = "\n".join([f"- {u}" for u in memory_units])
        
        # Note: Using persona_reconciler prompt key
        from core.brain.prompts.registry import get_prompt_registry
        p_registry = get_prompt_registry()
        prompt = p_registry.get("system.distiller.persona_reconciler", memory_units=units_str)

        try:
            logger.info(f"[DISTILLER] Reconciling persona from {len(memory_units)} units...")
            raw_response = await self.think(prompt, mood="ANALYTICAL", timeout=60.0)
            
            if raw_response in ["ERROR_TIMEOUT", "ERROR_FAILED"]:
                return {}

            from core.brain.utils import extract_json
            identity = extract_json(raw_response)
            return identity if isinstance(identity, dict) else {}
        except Exception as e:
            logger.error(f"[DISTILLER] Persona reconciliation failed: {e}")
            return {}

    async def consolidate_memories(self, memories: List[Dict[str, Any]], topic: str = "") -> List[Dict[str, Any]]:
        """
        Progressive Summarization — Layer 2: Merge related memories into consolidated highlights.
        Groups by category, then uses LLM to merge overlapping facts into fewer, richer entries.
        """
        if len(memories) < 3:
            return memories  # Not enough to consolidate
        
        # Group memories by category
        groups: Dict[str, List[str]] = {}
        for m in memories:
            cat = m.get("category", "CONTEXT")
            val = str(m.get("value", m.get("key", "")))
            if cat not in groups:
                groups[cat] = []
            groups[cat].append(val)
        
        consolidated = []
        for category, items in groups.items():
            if len(items) < 2:
                # Single item, keep as-is
                consolidated.append({"category": category, "value": items[0], "importance": 0.7})
                continue
            
            items_str = "\n".join([f"- {item}" for item in items[:20]])  # Cap at 20
            
            from core.brain.prompts.registry import get_prompt_registry
            p_registry = get_prompt_registry()
            
            prompt = p_registry.get(
                "system.distiller.memory_consolidation",
                category=category,
                topic=topic or "General",
                items_str=items_str
            )
            
            try:
                raw = await self.think(prompt, mood="ANALYTICAL", timeout=120.0)
                if raw in ["ERROR_TIMEOUT", "ERROR_FAILED"]:
                    consolidated.extend([{"category": category, "value": v, "importance": 0.5} for v in items])
                    continue
                
                from core.brain.utils import extract_json
                merged = extract_json(raw)
                if merged and isinstance(merged, list):
                    for m in merged:
                        m["category"] = category
                    consolidated.extend(merged)
                    logger.info(f"[DISTILLER] Consolidated {len(items)} → {len(merged)} facts in {category}")
                else:
                    consolidated.extend([{"category": category, "value": v, "importance": 0.5} for v in items])
            except Exception as e:
                logger.error(f"[DISTILLER] Consolidation failed for {category}: {e}")
                consolidated.extend([{"category": category, "value": v, "importance": 0.5} for v in items])
        
        return consolidated

    async def extract_essence(self, memories: List[Dict[str, Any]], max_beliefs: int = 10) -> List[Dict[str, Any]]:
        """
        Progressive Summarization — Layer 3: Ultra-compress to core beliefs.
        One sentence per topic — the agent's most fundamental knowledge.
        """
        if not memories:
            return []
        
        facts_str = "\n".join([f"- [{m.get('category', '?')}] {m.get('value', m.get('key', ''))}" for m in memories[:50]])
        
        from core.brain.prompts.registry import get_prompt_registry
        p_registry = get_prompt_registry()
        
        prompt = p_registry.get(
            "system.distiller.essence_extraction",
            facts_str=facts_str,
            max_beliefs=max_beliefs
        )
        
        try:
            raw = await self.think(prompt, mood="ANALYTICAL", timeout=60.0)
            if raw in ["ERROR_TIMEOUT", "ERROR_FAILED"]:
                return []
            
            from core.brain.utils import extract_json
            beliefs = extract_json(raw)
            if beliefs and isinstance(beliefs, list):
                logger.info(f"[DISTILLER] Extracted {len(beliefs)} core beliefs from {len(memories)} memories.")
                return beliefs
            return []
        except Exception as e:
            logger.error(f"[DISTILLER] Essence extraction failed: {e}")
            return []

