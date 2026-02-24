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
        prompt = f"""
        Analyze the following interaction between a User (Sếp) and an AI Assistant (Niva).
        Extract atomic memory units in JSON format.

        CATEGORIES:
        - FACT: Personal info, preferences, project details.
        - SENTIMENT: User's mood, attitude, or emotional state.
        - EXPERIENCE: Successful actions, optimal solutions discovered.
        - REFLECTION: Errors, mistakes, or lessons learned.

        INPUT:
        User: "{user_text}"
        Niva: "{agent_response}"

        RULES:
        1. Resolve relative dates (today, tomorrow) to absolute dates if possible (Current Date: {datetime.utcnow().date()}).
        2. Resolve coreferences (he, she, it, that) to specific entities.
        3. Keep facts atomic and context-independent.
        4. Output strictly a JSON list of objects: [{{"category": "...", "content": "...", "importance": 0.0-1.0}}]
        5. If nothing important found, return an empty list [].
        """
        
        try:
            raw_response = await self.think(prompt, mood="NEUTRAL", timeout=120.0)
            
            # Basic JSON cleanup (handling potential markdown fences)
            clean_json = raw_response.strip()
            if "```" in clean_json:
                clean_json = clean_json.split("```")[1]
                if clean_json.startswith("json"):
                    clean_json = clean_json[4:]
            
            units = json.loads(clean_json)
            if not isinstance(units, list):
                logger.warning(f"[DISTILLER] Expected list, got {type(units)}")
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

        Output a JSON list of objects: [{{"category": "EXPERIENCE" or "REFLECTION", "content": "...", "importance": 0.8-1.0}}]
        """
        try:
            logger.info(f"[DISTILLER] Distilling reflection for task: {task_description[:50]}...")
            raw_response = await self.think(prompt, mood="ANALYTICAL", timeout=120.0)
            logger.info(f"[DISTILLER] Raw Reflection Response: {raw_response[:100]}...")
            
            clean_json = raw_response.strip()
            if "```" in clean_json:
                clean_json = clean_json.split("```")[1]
                if clean_json.startswith("json"):
                    clean_json = clean_json[4:]
            
            lessons = json.loads(clean_json)
            logger.info(f"[DISTILLER] Extracted {len(lessons)} lessons.")
            return lessons
        except Exception as e:
            logger.error(f"[DISTILLER] Reflection distillation failed: {e}")
            return []
