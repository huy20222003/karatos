"""
Persistent Memory Module
Long-term memory storage using PostgreSQL.
Allows the agent to remember context across restarts.
"""
import os
import json
import re
from datetime import datetime, timedelta
from typing import Any, Optional
from dataclasses import dataclass
from enum import Enum
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

from config.settings import settings
from utils.logger import get_logger

from config.settings import settings
from utils.logger import get_logger

logger = get_logger()


class MemoryCategory(str, Enum):
    """
    Human-Like Cognitive Memory Categories.
    Organized by brain function — mirrors how humans store and recall information.
    """
    # ═══ EPISODIC MEMORY (What happened) ═══
    CONTEXT = "CONTEXT"           # Current session/conversation context (short-term)
    EXPERIENCE = "EXPERIENCE"     # Past events and technical encounters (long-term)
    DECISION = "DECISION"         # Choices made and their outcomes
    EMOTION = "EMOTION"           # How events felt — joy, frustration, satisfaction

    # ═══ SEMANTIC MEMORY (What I know) ═══
    LEARNING = "LEARNING"         # Verified knowledge, confirmed facts
    FACT = "FACT"                 # Objective facts about user/world/environment
    PROCEDURAL = "PROCEDURAL"     # How-to knowledge — step-by-step workflows

    # ═══ IDENTITY MEMORY (Who I am) ═══
    PERSONA = "PERSONA"           # Bot's name, tone, personality style
    REFLECTION = "REFLECTION"     # Self-improvement lessons, behavioral corrections
    BELIEF = "BELIEF"             # Core values and guiding principles

    # ═══ SOCIAL MEMORY (Who they are) ═══
    USER_PROFILE = "USER_PROFILE" # User preferences, attributes, stated constraints
    USER_HISTORY = "USER_HISTORY" # User action history and interactions
    RELATIONSHIP = "RELATIONSHIP" # Social dynamics — trust, closeness, roles
    SENTIMENT = "SENTIMENT"       # Current emotional state tracking (mood)

    # ═══ EXECUTIVE MEMORY (What I want) ═══
    GOAL = "GOAL"                 # Active objectives, ongoing projects
    HABIT = "HABIT"               # Recurring patterns, routines, behavioral tendencies

    # ═══ SYSTEM MEMORY (Technical state) ═══
    SYSTEM = "SYSTEM"             # Infrastructure/platform state
    METADATA = "METADATA"         # Technical details, system context
    A2A = "A2A"                   # Agent-to-agent communication records


@dataclass
class MemoryEntry:
    """A single memory entry"""
    id: str
    key: str
    value: Any
    category: MemoryCategory
    importance: float
    created_at: datetime
    expires_at: Optional[datetime] = None
    score: float = 0.0 # Cosine distance (lower is better) or similarity


class PersistentMemory:
    """
    Long-term memory for Brain.
    Uses Markdown storage for persistence across restarts.
    (PostgreSQL dependency removed for simplified architecture).
    """
    
    def __init__(self, base_path: str = "data/storage"):
        """Initialize with Markdown storage"""
        # Markdown Storage (Primary & Only Source of Truth)
        from utils.markdown_memory import MarkdownMemory
        self.md_storage = MarkdownMemory(base_path=base_path)
        
        # Memory Distiller (Memory 3.0)
        from utils.distiller import MemoryDistiller
        self.distiller = MemoryDistiller()
        
        # Personality Evolution (Digital Soul)
        from utils.evolution import PersonalityEvolution
        self.evolution = PersonalityEvolution()
        
        logger.info("[MEMORY] PersistentMemory initialized using Markdown-only storage.")
        
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
        Store a memory in Markdown files with deduplication.
        Before storing, checks if a similar memory exists (keyword overlap > 70%).
        If similar: updates importance instead of creating duplicate.
        """
        expires_at = None
        if expires_in_days:
            expires_at = datetime.utcnow() + timedelta(days=expires_in_days)
        
        # Deduplication check — skip for session/context data
        if category not in (MemoryCategory.CONTEXT, MemoryCategory.USER_HISTORY):
            similar = self._find_similar(key, str(value), category)
            if similar:
                logger.debug(f"[MEMORY] Dedup: Similar memory found for '{key[:40]}', skipping duplicate.")
                return f"md:dedup:{similar.key}"
            
        try:
            # Sync to Markdown (Source of Truth)
            from utils.markdown_memory import MarkdownMemoryEntry
            self.md_storage.append(MarkdownMemoryEntry(
                key=key,
                category=category.value,
                importance=importance,
                created_at=datetime.utcnow().isoformat(),
                value=value,
                expires_at=expires_at.isoformat() if expires_at else None
            ))
            
            logger.debug(f"[MEMORY] Stored in Markdown: {key} (category: {category.value})")
            return f"md:{key}"
                
        except Exception as e:
            logger.error(f"[MEMORY] Failed to store memory: {e}")
            raise

    def _find_similar(self, key: str, value: str, category: MemoryCategory) -> Optional[Any]:
        """
        Deduplication via Jaccard Similarity on keyword sets.
        Returns existing similar entry if overlap > 0.7, else None.
        """
        try:
            # Extract keywords from new memory
            new_text = f"{key} {value}".lower()
            new_words = set(w for w in re.findall(r'\w+', new_text) if len(w) > 2)
            
            if len(new_words) < 3:
                return None  # Too few keywords to compare meaningfully
            
            # Search existing memories for potential duplicates
            existing = self.md_storage.search_by_keywords(list(new_words)[:5], limit=10)
            
            for entry in existing:
                if entry.category != category.value:
                    continue
                    
                entry_text = f"{entry.key} {str(entry.value)}".lower()
                entry_words = set(w for w in re.findall(r'\w+', entry_text) if len(w) > 2)
                
                if not entry_words:
                    continue
                
                # Jaccard similarity = |A ∩ B| / |A ∪ B|
                intersection = new_words & entry_words
                union = new_words | entry_words
                similarity = len(intersection) / len(union) if union else 0
                
                # Require both high similarity AND meaningful overlap (min 5 shared words)
                if similarity > 0.75 and len(intersection) >= 5:
                    return entry
                    
        except Exception as e:
            logger.debug(f"[MEMORY] Dedup check failed: {e}")
        
        return None
            
    async def recall(self, key: str) -> Optional[Any]:
        """
        Retrieve a specific memory from Markdown Source of Truth.
        """
        logger.debug(f"[MEMORY] Recalling {key} from Markdown...")
        entry = self.md_storage.find_by_key(key)
        if entry:
            return entry.value
            
        return None
            
    async def forget(self, key: str) -> bool:
        """Markdown modification is not yet optimized for single-key deletion."""
        logger.warning(f"[MEMORY] Forget command ignored for {key} (Markdown deletion not implemented).")
        return False
            
    async def search(
        self,
        query: str = "",
        category: Optional[MemoryCategory] = None,
        min_importance: float = 0.0,
        limit: int = 50
    ) -> list[MemoryEntry]:
        """
        Search memories with optional query, category filter, and importance threshold.
        """
        search_text = query or (category.value if category else "")
        results = await self.deep_recall(query_text=search_text, limit=limit * 2)
        
        # Apply category filter
        if category:
            results = [r for r in results if r.category == category]
        
        # Apply importance filter
        if min_importance > 0:
            results = [r for r in results if r.importance >= min_importance]
        
        return results[:limit]

    async def search_semantic(
        self,
        query_text: str,
        category: Optional[MemoryCategory] = None,
        limit: int = 5,
        threshold: Optional[float] = None,
        query_vector: Optional[list[float]] = None
    ) -> list[MemoryEntry]:
        """
        Fallback to keyword search (Semantic search removed with DB/Vector dependency).
        """
        logger.debug("[MEMORY] Semantic search falling back to deep_recall.")
        return await self.deep_recall(query_text, limit=limit)
            
    async def rrf_search(
        self,
        query_text: str,
        categories: list[MemoryCategory] = None,
        limit: int = 10,
        k: int = 60
    ) -> list[MemoryEntry]:
        """
        Fallback to deep_recall.
        """
        return await self.deep_recall(query_text, limit=limit)

    async def deep_recall(
        self, 
        query_text: str, 
        limit: int = 15,
        query_vector: Optional[list[float]] = None
    ) -> list[MemoryEntry]:
        """
        Critical Markdown Memory Recall with relevance scoring.
        Uses keyword matching with scoring (better matches ranked higher).
        """
        import re
        
        # 1. Clean keywords from query text (language-agnostic)
        keywords = [w.lower() for w in re.findall(r'\w+', query_text) if len(w) > 2]
        
        if not keywords:
            keywords = ["memory"]
            
        # Fetch more results for scoring
        md_matches = self.md_storage.search_by_keywords(keywords, limit=limit * 3)
        
        results = []
        for entry in md_matches:
            cat_enum = MemoryCategory.CONTEXT
            try:
                cat_enum = MemoryCategory(entry.category)
            except:
                pass
            
            # Score by keyword match count
            entry_text = f"{entry.key} {str(entry.value)}".lower()
            match_count = sum(1 for kw in keywords if kw in entry_text)
            relevance_score = match_count / max(len(keywords), 1)
                
            results.append(MemoryEntry(
                id=f"md:{entry.key}",
                key=entry.key,
                value=entry.value,
                category=cat_enum,
                importance=entry.importance,
                created_at=datetime.fromisoformat(entry.created_at) if entry.created_at else datetime.utcnow(),
                score=relevance_score
            ))
        
        # Sort by relevance score (higher = better match), then by importance
        results.sort(key=lambda x: (x.score, x.importance), reverse=True)
        return results[:limit]

    # ==========================================
    # USER HISTORY OPERATIONS
    # ==========================================
    
    async def record_user_action(
        self,
        user_id: str,
        action: str,
        details: dict = None
    ):
        """Record a user action in memory"""
        key = f"user_action:{user_id}:{datetime.utcnow().isoformat()}"
        await self.remember(
            key=key,
            value={"action": action, "details": details or {}},
            category=MemoryCategory.USER_HISTORY,
            importance=0.3,
            expires_in_days=30  # Keep for 30 days
        )
        
    async def get_user_warning_count(self, user_id: str) -> int:
        """Get the number of warnings for a user"""
        key = f"user_warnings:{user_id}"
        count = await self.recall(key)
        return count if count else 0
        
    async def increment_user_warning(self, user_id: str) -> int:
        """Increment warning count for a user"""
        key = f"user_warnings:{user_id}"
        current = await self.get_user_warning_count(user_id)
        new_count = current + 1
        
        await self.remember(
            key=key,
            value=new_count,
            category=MemoryCategory.USER_HISTORY,
            importance=0.7  # Warnings are important
        )
        return new_count
        
    async def get_user_risk_score(self, user_id: str) -> float:
        """Get current risk score for a user (0.0 to 1.0)"""
        key = f"risk_score:{user_id}"
        score = await self.recall(key)
        return float(score) if score is not None else 0.0

    async def update_user_risk_score(self, user_id: str, change: float):
        """Update user risk score with decay logic"""
        current = await self.get_user_risk_score(user_id)
        # New score = current + change, clamped 0.0 to 1.0
        new_score = max(0.0, min(1.0, current + change))
        
        await self.remember(
            key=f"risk_score:{user_id}",
            value=new_score,
            category=MemoryCategory.USER_HISTORY,
            importance=0.8
        )

    async def get_user_history_summary(self, user_id: str) -> dict:
        """Get a summary of user's history with the agent"""
        warnings = await self.get_user_warning_count(user_id)
        risk_score = await self.get_user_risk_score(user_id)
        
        return {
            "user_id": user_id,
            "warning_count": warnings,
            "risk_score": risk_score,
            "recent_actions": [], # Actions tracking via markdown to be enhanced
            "risk_level": "very_high" if risk_score > 0.8 else "high" if risk_score > 0.5 or warnings >= 3 else "medium" if risk_score > 0.2 else "low"
        }
        
    # ==========================================
    # DECISION HISTORY OPERATIONS
    # ==========================================
    
    async def record_decision(
        self,
        target_type: str,
        target_id: str,
        action: str,
        reason: str,
        confidence: float,
        outcome: str = "PENDING"
    ) -> str:
        """
        Record an agent decision to persistent memory.
        Stored as a memory entry with category DECISION.
        
        Returns:
            The memory key (decision ID)
        """
        decision_id = f"dec:{datetime.utcnow().strftime('%Y%m%d%H%M%S')}:{target_id[:8]}"
        value = {
            "target_type": target_type.upper(),
            "target_id": target_id,
            "action": action,
            "reason": reason,
            "confidence": confidence,
            "outcome": outcome.upper(),
            "created_at": datetime.utcnow().isoformat()
        }
        
        await self.remember(
            key=decision_id,
            value=value,
            category=MemoryCategory.DECISION,
            importance=min(1.0, confidence)
        )
        
        logger.info(f"[MEMORY] Recorded decision: {action} on {target_type}:{target_id}")
        return decision_id
            
    async def update_decision_outcome(self, decision_id: str, outcome: str) -> bool:
        """Update the outcome of a previous decision in memory and distill lessons."""
        try:
            current_val = await self.recall(decision_id)
            if not current_val or not isinstance(current_val, dict):
                logger.warning(f"[MEMORY] Cannot update outcome: Decision {decision_id} not found.")
                return False
                
            current_val["outcome"] = outcome.upper()
            current_val["updated_at"] = datetime.utcnow().isoformat()
            
            await self.remember(
                key=decision_id,
                value=current_val,
                category=MemoryCategory.DECISION
            )
            
            # Real-time Distillation of Reflection (Memory 3.0)
            if outcome.upper() in ["SUCCESS", "FAILED", "ERROR"]:
                try:
                    task_info = f"Action: {current_val.get('action')} on {current_val.get('target_type')}:{current_val.get('target_id')}"
                    reasoning = current_val.get('reason', 'No reasoning provided')
                    
                    lessons = await self.distiller.distill_reflection(
                        task_description=f"{task_info} (Context: {reasoning})",
                        outcome=outcome.upper(),
                        errors=str(current_val.get('error')) if 'error' in current_val else None
                    )
                    
                    for lesson in lessons:
                        cat_str = lesson.get("category", "REFLECTION").upper()
                        try:
                            cat = MemoryCategory[cat_str]
                        except KeyError:
                            cat = MemoryCategory.REFLECTION
                            
                        await self.remember(
                            key=f"lesson:{decision_id}:{datetime.utcnow().timestamp()}",
                            value=lesson.get("content"),
                            category=cat,
                            importance=lesson.get("importance", 0.9)
                        )
                    
                    # Track technical growth
                    self.evolution.evolve("reliability" if outcome.upper() == "SUCCESS" else "maturity", 0.02, f"Processed decision outcome: {outcome}")
                    self.evolution.record_interaction(is_task=True)
                except Exception as dist_e:
                    logger.warning(f"[MEMORY] Reflection distillation failed for {decision_id}: {dist_e}")
                    
            return True
        except Exception as e:
            logger.error(f"[MEMORY] Failed to update decision outcome: {e}")
            return False
            
    async def get_decision_history(
        self,
        target_id: Optional[str] = None,
        action: Optional[str] = None,
        limit: int = 20
    ) -> list[dict]:
        """Get decision history from Markdown storage"""
        try:
            # Decisions are usually in history.md
            file_path = self.md_storage._get_file_path("DECISION", "dec:")
            entries = self.md_storage.load_all_from_file(file_path)
            
            decisions = []
            for entry in reversed(entries):
                val = entry.value
                if not isinstance(val, dict): continue
                
                # Filters
                if target_id and val.get("target_id") != target_id: continue
                if action and val.get("action") != action: continue
                
                val["id"] = entry.key
                val["created_at"] = entry.created_at
                decisions.append(val)
                
                if len(decisions) >= limit:
                    break
                    
            return decisions
        except Exception as e:
            logger.error(f"[MEMORY] Failed to get decision history: {e}")
            return []
            
            
    async def get_daily_actions(self, hours: int = 24) -> list[dict]:
        """Get all decisions from memory in the last N hours"""
        cutoff = datetime.utcnow() - timedelta(hours=hours)
        decisions = await self.get_decision_history(limit=100)
        
        results = []
        for d in decisions:
            try:
                dt = datetime.fromisoformat(d.get("created_at", ""))
                if dt >= cutoff:
                    results.append(d)
            except:
                continue
        return results
            
    # ==========================================
    # CONTEXT FOR AI
    # ==========================================
    
    async def get_relevant_context(self, user_id: Optional[str] = None) -> dict:
        """
        Get relevant context for AI reasoning.
        This is injected into the brain pipeline.
        """
        context = {
            "timestamp": datetime.utcnow().isoformat(),
            "recent_decisions": await self.get_decision_history(limit=5),
            "important_memories": []
        }
        
        # Get high-importance memories
        important = await self.search(min_importance=0.7, limit=10)
        context["important_memories"] = [
            {"key": m.key, "value": m.value, "category": m.category.value}
            for m in important
        ]
        
        # Add user-specific context if provided
        if user_id:
            context["user_context"] = await self.get_user_history_summary(user_id)
            
        return context

    # ==========================================
    # CONVERSATION MEMORY (Chat)
    # ==========================================
    
    async def record_chat_message(self, chat_id: str, role: str, content: str):
        """Record a message in the conversation history and distill knowledge."""
        # 1. Store the raw message
        key = f"chat:{chat_id}:{datetime.utcnow().timestamp()}"
        await self.remember(
            key=key,
            value={"role": role, "content": content},
            category=MemoryCategory.CONTEXT,
            importance=0.2,
            expires_in_days=None
        )
        
        # 2. Real-time Distillation (Memory 3.0)
        # If it's an assistant response, distill the User-Assistant pair
        if role.lower() in ["assistant", "niva"]:
            logger.info(f"[MEMORY] Triggering distillation for chat {chat_id}...")
            try:
                # Find the last message from user in this chat
                history = await self.get_chat_history(chat_id, limit=5)
                user_msg = None
                for msg in history:
                    if msg.get("role") == "user":
                        user_msg = msg.get("content")
                        break
                
                if user_msg:
                    units = await self.distiller.distill_interaction(user_msg, content)
                    for unit in units:
                        cat_str = unit.get("category", "LEARNING").upper()
                        try:
                            cat = MemoryCategory[cat_str]
                        except KeyError:
                            cat = MemoryCategory.LEARNING
                            
                        await self.remember(
                            key=f"distilled:{chat_id}:{datetime.utcnow().timestamp()}",
                            value=unit.get("content"),
                            category=cat,
                            importance=unit.get("importance", 0.5)
                        )
                # Track communication growth
                self.evolution.evolve("empathy", 0.01, "Engaged in user interaction.")
                self.evolution.record_interaction(is_task=False)
            except Exception as e:
                logger.warning(f"[MEMORY] Distillation failed for chat {chat_id}: {e}")
        
    async def get_chat_history(self, chat_id: str, limit: int = 15) -> list[dict]:
        """
        Retrieve recent chat history for a session from Markdown session file.
        """
        try:
            # 1. Map chat_id to markdown session file
            file_path = self.md_storage._get_file_path("context", f"chat:{chat_id}:now")
            # OPTIMIZATION: Only load relevant tail from markdown file
            entries = self.md_storage.load_all_from_file(file_path, limit_last=limit)
            
            if entries:
                # Sort by created_at and take last N
                entries.sort(key=lambda x: x.created_at)
                history = [e.value for e in entries[-limit:]]
                logger.debug(f"[MEMORY] Recovered {len(history)} messages for chat {chat_id}.")
                return history
                
        except Exception as e:
            logger.error(f"[MEMORY] Chat history retrieval failed for {chat_id}: {e}")
            
        return []
        
    # ==========================================
    # MAINTENANCE
    # ==========================================
    
    async def cleanup_expired(self) -> int:
        """Markdown cleanup (placeholder)"""
        return 0
            
    async def get_stats(self) -> dict:
        """Get memory statistics from Markdown files"""
        return {
            "total_memories": "N/A (Markdown Mode)",
            "total_decisions": len(await self.get_decision_history(limit=1000))
        }


# Singleton instance
_memory_instance: Optional[PersistentMemory] = None


def get_memory(base_path: str = "data/storage") -> PersistentMemory:
    """Get the global memory instance, or create one with specific paths"""
    global _memory_instance
    if _memory_instance is None:
        _memory_instance = PersistentMemory(base_path=base_path)
    return _memory_instance
