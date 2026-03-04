import os
import json
import re
import numpy as np
from datetime import datetime, timedelta
from typing import Any, Optional, List
from dataclasses import dataclass
from enum import Enum

from config.settings import settings
from utils.logger import get_logger
from utils.embeddings import get_embedding_engine
from memory.file_vector_engine import FileVectorEngine, FileVectorEntry

logger = get_logger()

class MemoryCategory(str, Enum):
    """
    Human-Like Cognitive Memory Categories.
    Organized by brain function — mirrors how humans store and recall information.
    """
    CONTEXT = "CONTEXT"           # Current session/conversation context
    EXPERIENCE = "EXPERIENCE"     # Past events and technical encounters
    DECISION = "DECISION"         # Choices made and their outcomes
    EMOTION = "EMOTION"           # How events felt
    LEARNING = "LEARNING"         # Verified knowledge, confirmed facts
    FACT = "FACT"                 # Objective facts
    PROCEDURAL = "PROCEDURAL"     # How-to knowledge
    PERSONA = "PERSONA"           # Bot's identity
    REFLECTION = "REFLECTION"     # Self-improvement lessons
    BELIEF = "BELIEF"             # Core values
    USER_PROFILE = "USER_PROFILE" # User preferences
    USER_HISTORY = "USER_HISTORY" # User action history
    RELATIONSHIP = "RELATIONSHIP" # Social dynamics
    SENTIMENT = "SENTIMENT"       # Current emotional state tracking
    GOAL = "GOAL"                 # Active objectives
    HABIT = "HABIT"               # Recurring patterns
    SYSTEM = "SYSTEM"             # Technical state
    METADATA = "METADATA"         # Technical details
    A2A = "A2A"                   # Agent-to-agent
    INTUITION = "INTUITION"       # Hunches
    VAULT = "VAULT"               # Encrypted secrets

@dataclass
class MemoryEntry:
    """A single memory entry for external consumption"""
    id: str
    key: str
    value: Any
    category: MemoryCategory
    importance: float
    created_at: datetime
    expires_at: Optional[datetime] = None
    score: float = 0.0

class PersistentMemory:
    """
    Long-term memory for Brain.
    Transitioned to Vector-First Architecture (SQLite + Local Embeddings).
    """
    
    def __init__(self, base_path: str = "data/storage"):
        self.engine = FileVectorEngine(base_path=base_path)
        self.embedder = get_embedding_engine()
        
        # Helper components
        from utils.distiller import MemoryDistiller
        from utils.evolution import PersonalityEvolution
        self.distiller = MemoryDistiller()
        self.evolution = PersonalityEvolution()
        
        logger.info("[MEMORY] PersistentMemory initialized using Pure File Vector storage.")

    # ==========================================
    # CORE MEMORY OPERATIONS
    # ==========================================
    
    async def remember(
        self,
        key: str,
        value: Any,
        category: MemoryCategory = MemoryCategory.CONTEXT,
        importance: float = 0.5,
        expires_in_days: Optional[int] = None,
        embedding_text: Optional[str] = None
    ) -> str:
        """
        Store a memory with its vector embedding.
        """
        expires_at = None
        if expires_in_days:
            expires_at = (datetime.utcnow() + timedelta(days=expires_in_days)).isoformat()
        
        created_at = datetime.utcnow().isoformat()
        
        # 1. Generate text for embedding (defaults to key + value)
        text_to_embed = embedding_text or f"{key} {str(value)}"
        vector = await self.embedder.get_embedding(text_to_embed)
        
        # 2. Vector-based Deduplication (Similarity > 0.95)
        if category not in (MemoryCategory.CONTEXT, MemoryCategory.USER_HISTORY):
            similar = await self.search_semantic(text_to_embed, category=category, limit=1, threshold=0.96)
            if similar:
                logger.debug(f"[MEMORY] Dedup: Similar memory found for '{key[:40]}'. Updating instead.")
                key = similar[0].key # Reuse existing key to UPSERT
        
        # 3. Store in FileVectorEngine
        entry = FileVectorEntry(
            key=key,
            category=category.value,
            content=value,
            importance=importance,
            vector=np.array(vector),
            created_at=created_at,
            expires_at=expires_at
        )
        self.engine.upsert(entry)
        
        logger.debug(f"[MEMORY] Remembered: {key} (Vector-based)")
        return key

    async def recall(self, key: str, category: Optional[MemoryCategory] = None) -> Optional[Any]:
        """Retrieve a specific memory by key. Search all categories if none provided."""
        if category:
            entry = self.engine.get(key, category.value)
            return entry.content if entry else None
        
        # If category not known, we have to search (or we assume standard mapping)
        # For efficiency, we try to match category from common types if key prefix exists
        for cat in MemoryCategory:
            entry = self.engine.get(key, cat.value)
            if entry:
                return entry.content
        return None

    async def forget(self, key: str, category: MemoryCategory) -> bool:
        """Delete a memory entry."""
        return self.engine.delete(key, category.value)

    async def search_semantic(
        self,
        query_text: str,
        category: Optional[MemoryCategory] = None,
        limit: int = 5,
        threshold: Optional[float] = 0.5,
        query_vector: Optional[list[float]] = None
    ) -> List[MemoryEntry]:
        """
        True Semantic Search using locally generated vectors.
        """
        if query_vector is None:
            query_vector = await self.embedder.get_embedding(query_text)
        
        if query_vector is None:
            logger.warning("[MEMORY] Semantic search skipped: No query vector available.")
            return []
            
        q_vec = np.array(query_vector)
        cat_str = category.value if category else None
        
        results = self.engine.search(q_vec, limit=limit, category=cat_str)
        
        final_results = []
        for r in results:
            if threshold and r.score < threshold:
                continue
                
            entry = self._vector_to_memory(r)
            final_results.append(entry)
            
        return final_results

    async def deep_recall(
        self, 
        query_text: str, 
        limit: int = 15,
        query_vector: Optional[list[float]] = None
    ) -> List[MemoryEntry]:
        """
        High-quality recall combining semantic relevance and importance.
        """
        # In Vector-First world, deep_recall is semantic search with a broader net
        return await self.search_semantic(query_text, limit=limit, threshold=0.1, query_vector=query_vector)

    async def search(
        self,
        query: str = "",
        category: Optional[MemoryCategory] = None,
        min_importance: float = 0.0,
        limit: int = 50
    ) -> List[MemoryEntry]:
        """General search with filtering."""
        if query:
            return await self.search_semantic(query, category=category, limit=limit, threshold=min_importance)
        
        # List by category if no query
        cat_str = category.value if category else None
        if cat_str:
            results = self.engine.list_by_category(cat_str, limit=limit)
            return [self._vector_to_memory(r) for r in results if r.importance >= min_importance]
        
        return []

    # ==========================================
    # USER & DECISION & CHAT HELPERS
    # ==========================================
    
    def _vector_to_memory(self, r: FileVectorEntry) -> MemoryEntry:
        """Convert engine entry to domain entry."""
        try: cat = MemoryCategory(r.category)
        except: cat = MemoryCategory.CONTEXT
        
        return MemoryEntry(
            id=r.key,
            key=r.key,
            value=r.content,
            category=cat,
            importance=r.importance,
            created_at=datetime.fromisoformat(r.created_at) if r.created_at else datetime.utcnow(),
            expires_at=datetime.fromisoformat(r.expires_at) if r.expires_at else None,
            score=r.score
        )

    # Simplified re-implementations using the same pattern
    async def record_user_action(self, user_id: str, action: str, details: dict = None):
        key = f"user_action:{user_id}:{datetime.utcnow().timestamp()}"
        await self.remember(key, {"action": action, "details": details or {}}, MemoryCategory.USER_HISTORY, 0.3)

    async def record_decision(self, target_type: str, target_id: str, action: str, reason: str, confidence: float, outcome: str = "PENDING") -> str:
        decision_id = f"dec:{datetime.utcnow().timestamp()}:{target_id[:8]}"
        value = {"target_type": target_type, "target_id": target_id, "action": action, "reason": reason, "confidence": confidence, "outcome": outcome}
        await self.remember(decision_id, value, MemoryCategory.DECISION, confidence)
        return decision_id

    async def record_chat_message(self, chat_id: str, role: str, content: str, episode_id: Optional[str] = None, metadata: Optional[dict] = None):
        key = f"chat:{chat_id}:{datetime.utcnow().timestamp()}"
        value = {"role": role, "content": content}
        
        # Combine explicitly provided metadata with episode_id
        meta = metadata.copy() if metadata else {}
        if episode_id: meta["episode_id"] = episode_id
        
        if meta: value["metadata"] = meta
        
        await self.remember(key, value, MemoryCategory.CONTEXT, 0.2)
        
        # Distillation (Memory 3.0)
        if role.lower() in ["assistant", "niva"]:
            try:
                history = await self.get_chat_history(chat_id, limit=5)
                user_msg = next((m["content"] for m in reversed(history) if m["role"] == "user"), None)
                if user_msg:
                    units = await self.distiller.distill_interaction(user_msg, content)
                    for unit in units:
                        await self.remember(f"distilled:{chat_id}:{datetime.utcnow().timestamp()}", unit["content"], MemoryCategory[unit.get("category", "LEARNING").upper()], unit.get("importance", 0.5))
                self.evolution.record_interaction(is_task=False)
            except Exception as e: logger.warning(f"Distillation failed: {e}")

    async def get_chat_history(self, chat_id: str, limit: int = 15, episode_id: Optional[str] = None) -> List[dict]:
        """Retrieve recent chat history for a session."""
        # This is a bit inefficient without index on prefix, but fine for local scale
        # Better: use SQLite LIKE or specialized method if needed.
        # For now, list_by_category and filter in memory as it's SQLite.
        results = self.engine.list_by_category("CONTEXT", limit=limit * 2)
        history = []
        prefix = f"chat:{chat_id}:"
        for r in results:
            if r.key.startswith(prefix):
                if episode_id and r.content.get("metadata", {}).get("episode_id") != episode_id:
                    continue
                history.append(r.content)
            if len(history) >= limit: break
            
        history.reverse() # Back to chronological
        return history

    async def get_user_warning_count(self, user_id: str) -> int:
        val = await self.recall(f"user_warnings:{user_id}")
        return int(val) if val else 0

    async def get_user_risk_score(self, user_id: str) -> float:
        val = await self.recall(f"risk_score:{user_id}", MemoryCategory.METADATA)
        return float(val) if val is not None else 0.0

    async def get_user_history_summary(self, user_id: str) -> dict:
        return {
            "user_id": user_id, 
            "warning_count": await self.get_user_warning_count(user_id),
            "risk_score": await self.get_user_risk_score(user_id)
        }

    async def get_stats(self) -> dict:
        return {"total_memories": self.engine.get_count()}

_memory_instance: Optional[PersistentMemory] = None

def get_memory(base_path: str = "data/storage") -> PersistentMemory:
    global _memory_instance
    if _memory_instance is None:
        _memory_instance = PersistentMemory(base_path=base_path)
    return _memory_instance
