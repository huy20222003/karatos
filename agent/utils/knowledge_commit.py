"""
Knowledge Commit Utility
Lets the Brain decide which tool results are worth storing as long-term
knowledge, and writes distilled units into PersistentMemory.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from utils.logger import get_logger
from utils.distiller import MemoryDistiller
from memory.persistent import PersistentMemory, MemoryCategory

logger = get_logger()


async def commit_tool_knowledge(
    memory: PersistentMemory,
    user_message: str,
    raw_results: str,
) -> None:
    """
    Ask the Distiller/Brain to extract durable knowledge units from tool
    results for this user message, and commit them to persistent memory.

    - No hardcoded topic or skill name.
    - If the Brain decides nothing is worth storing, nothing is written.
    """
    if not memory or not raw_results or not user_message:
        return

    try:
        distiller = MemoryDistiller()
        # Treat tool results as an assistant-style response for the purposes
        # of distillation. The distiller will decide what to keep.
        units = await distiller.distill_interaction(user_message, raw_results[:4000])
        if not units:
            return

        ts = datetime.utcnow().timestamp()
        for idx, unit in enumerate(units):
            content = unit.get("content")
            if not content:
                continue
            cat_str = unit.get("category", "LEARNING").upper()
            try:
                category = MemoryCategory[cat_str]
            except KeyError:
                category = MemoryCategory.LEARNING

            importance = float(unit.get("importance", 0.5))
            key = f"knowledge:{ts}:{idx}"
            await memory.remember(
                key=key,
                value=content,
                category=category,
                importance=importance,
                expires_in_days=None,
                embedding_text=f"{user_message} → {content}"[:500],
            )

        logger.info(f"[KNOWLEDGE_COMMIT] Stored {len(units)} distilled units for query.")
    except Exception as e:
        logger.warning(f"[KNOWLEDGE_COMMIT] Commit failed: {e}")

