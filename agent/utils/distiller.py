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
        Distills a single interaction into multiple memory units.
        Returns a list of distilled facts/sentiments/reflections.
        """
        # Note: BrainModel.think will use system.distiller.prompt
        prompt = f"User: \"{user_text}\"\nAssistant: \"{agent_response}\""
        
        try:
            raw_response = await self.think(prompt, mood="NEUTRAL", timeout=180.0)
            
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
        prompt = f"""
        Analyze the outcome of an autonomous task.
        Extract lessons and experiences.

        TASK: {task_description}
        OUTCOME: {outcome}
        ERRORS/LOGS: {errors if errors else "None"}

        Output STRICTLY a JSON list of objects: [{{"category": "EXPERIENCE" or "REFLECTION", "content": "...", "importance": 0.8-1.0}}]
        """
        try:
            logger.info(f"[DISTILLER] Distilling reflection for task: {task_description[:50]}...")
            raw_response = await self.think(prompt, mood="ANALYTICAL", timeout=180.0)
            
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
