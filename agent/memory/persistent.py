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

from sqlalchemy import create_engine, text, Column
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base
from pgvector.sqlalchemy import Vector

from config.settings import settings
from utils.logger import get_logger

logger = get_logger()


class MemoryCategory(str, Enum):
    """Memory categories matching Prisma enum"""
    USER_HISTORY = "USER_HISTORY"
    DECISION = "DECISION"
    LEARNING = "LEARNING"
    CONTEXT = "CONTEXT"
    SYSTEM = "SYSTEM"
    A2A = "A2A"
    EXPERIENCE = "EXPERIENCE"
    REFLECTION = "REFLECTION"
    SENTIMENT = "SENTIMENT"


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
    Uses PostgreSQL to store memories that persist across restarts.
    
    Features:
    - Remember user behavior patterns
    - Store decision history for learning
    - Track context across sessions
    - Auto-expire old memories
    """
    
    def __init__(self, base_path: str = "data/storage"):
        """Initialize with shared DB factory and Markdown storage"""
        self.engine = create_engine(settings.database_url)
        self.Session = sessionmaker(bind=self.engine)
        
        # Markdown Storage (OpenClaw Style)
        from utils.markdown_memory import MarkdownMemory
        self.md_storage = MarkdownMemory(base_path=base_path)
        
        # Memory Distiller (Memory 3.0)
        from utils.distiller import MemoryDistiller
        self.distiller = MemoryDistiller()
        
        # Personality Evolution (Digital Soul)
        from utils.evolution import PersonalityEvolution
        self.evolution = PersonalityEvolution()
        
        # Dynamic SQL Mapping for Enum Constraints
        self._sql_category_map = {
            MemoryCategory.A2A: "CONTEXT",
            MemoryCategory.EXPERIENCE: "CONTEXT",
            MemoryCategory.REFLECTION: "CONTEXT",
            MemoryCategory.SENTIMENT: "CONTEXT"
        }
        
        try:
            self._init_vector_support()
        except Exception as e:
            logger.warning(f"[MEMORY] Vector support initialization skipped: {e}")
        
    def _init_vector_support(self):
        """Enable pgvector extension if not present and add vector column if missing."""
        try:
            with self._get_session() as session:
                # 1. Enable extension
                try:
                    session.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
                    session.commit()
                    logger.info("[MEMORY] pgvector extension enabled successfully.")
                except Exception as ext_err:
                    logger.warning(f"[MEMORY] Could not enable pgvector extension: {ext_err}")
                    logger.warning("[MEMORY] Ensure pgvector is installed on your PostgreSQL server.")
                    return # Stop here if extension fails
                
                # 2. Add embedding column to agent_memory if missing
                # Check if column exists
                check_col = """
                    SELECT column_name 
                    FROM information_schema.columns 
                    WHERE table_name='agent_memory' AND column_name='embedding';
                """
                res = session.execute(text(check_col))
                if not res.fetchone():
                    logger.info("[MEMORY] Adding 'embedding' column to agent_memory table...")
                    try:
                        # Using 768 dimensions for nomic-embed-text
                        session.execute(text("ALTER TABLE agent_memory ADD COLUMN embedding vector(768)"))
                        session.commit()
                        logger.info("[MEMORY] 'embedding' column added successfully.")
                    except Exception as col_err:
                        logger.error(f"[MEMORY] Failed to add embedding column: {col_err}")
                else:
                    logger.debug("[MEMORY] 'embedding' column already exists.")

                # 3. Create HNSW Index (Only if not exists)
                check_idx = """
                    SELECT indexname FROM pg_indexes 
                    WHERE tablename = 'agent_memory' AND indexname = 'agent_memory_embedding_idx';
                """
                if not session.execute(text(check_idx)).fetchone():
                    try:
                        index_sql = """
                            CREATE INDEX agent_memory_embedding_idx 
                            ON agent_memory 
                            USING hnsw (embedding vector_cosine_ops) 
                            WITH (m = 16, ef_construction = 64);
                        """
                        session.execute(text(index_sql))
                        session.commit()
                        logger.info("[MEMORY] HNSW Index initialized successfully.")
                    except Exception as idx_err:
                        error_msg = str(idx_err).lower()
                        if "must be owner" in error_msg:
                            logger.warning("[MEMORY] ⚠️  PERMISSION ERROR: Cannot create HNSW Index.")
                            logger.warning("[MEMORY] You already created it manually? If yes, ignore this.")
                            logger.warning("[MEMORY] SQL to fix ownership: ALTER TABLE agent_memory OWNER TO <user>;")
                        else:
                            logger.warning(f"[MEMORY] Could not create HNSW index: {idx_err}")
                        logger.warning("[MEMORY] Falling back to sequential scan (slower).")
                else:
                    logger.debug("[MEMORY] HNSW Index already exists. Skipping creation.")
                
                logger.info("[MEMORY] Vector support initialized successfully.")
        except Exception as e:
            logger.error(f"[MEMORY] Failed to initialize vector support: {e}")

    def _get_session(self):
        return self.Session()
        
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
        Store a memory.
        
        Args:
            key: Unique identifier (e.g., "user_warning_count:uuid")
            value: Data to store (will be JSON serialized)
            category: Type of memory
            importance: AI-rated importance (0-1)
            expires_in_days: Auto-expire after N days (None = never)
            embedding_text: Optional custom text to use for embedding (defaults to value)
            
        Returns:
            The memory ID
        """
        expires_at = None
        if expires_in_days:
            expires_at = datetime.utcnow() + timedelta(days=expires_in_days)
            
        try:
            # Generate embedding if it's context, learning, or A2A
            embedding = None
            if category in [MemoryCategory.LEARNING, MemoryCategory.USER_HISTORY, MemoryCategory.CONTEXT, MemoryCategory.A2A]:
                from utils.embeddings import get_embedding_engine
                engine = get_embedding_engine()
                
                # Use custom text if provided, otherwise derive from value
                if embedding_text:
                    text_to_embed = embedding_text
                elif isinstance(value, str):
                    text_to_embed = value
                elif isinstance(value, dict) and "role" in value and "content" in value:
                    # Special formatting for chat context to help semantic search
                    text_to_embed = f"{str(value['role']).upper()}: {value['content']}"
                else:
                    text_to_embed = json.dumps(value)
                
                embedding_vec = await engine.get_embedding(text_to_embed)
                embedding = str(embedding_vec) if embedding_vec else None

            # --- SQL Mapping for Enum Constraints ---
            sql_category = self._sql_category_map.get(category, category.value)

            with self._get_session() as session:
                query = """
                    INSERT INTO agent_memory (key, value, category, importance, expires_at, embedding, updated_at)
                    VALUES (:key, :value, :category, :importance, :expires_at, :embedding, NOW())
                    ON CONFLICT (key) DO UPDATE SET
                        value = :value,
                        importance = :importance,
                        embedding = :embedding,
                        updated_at = NOW()
                    RETURNING id
                """
                result = session.execute(text(query), {
                    "key": key,
                    "value": json.dumps(value),
                    "category": sql_category,
                    "importance": importance,
                    "expires_at": expires_at,
                    "embedding": embedding
                })
                session.commit()
                row = result.fetchone()
                memory_id = str(row[0]) if row else None
                
                # --- SYNC TO MARKDOWN (OpenClaw Style) ---
                from utils.markdown_memory import MarkdownMemoryEntry
                self.md_storage.append(MarkdownMemoryEntry(
                    key=key,
                    category=category.value,
                    importance=importance,
                    created_at=datetime.utcnow().isoformat(),
                    value=value,
                    expires_at=expires_at.isoformat() if expires_at else None
                ))
                
                logger.debug(f"[MEMORY] Stored: {key} (category: {category.value}) - Synced to MD")
                return memory_id
                
        except Exception as e:
            logger.error(f"[MEMORY] Failed to store memory: {e}")
            raise
            
    async def recall(self, key: str) -> Optional[Any]:
        """
        Retrieve a specific memory by key.
        Checks DB cache first, then falls back to Markdown Source of Truth.
        """
        # 1. Check DB Cache
        query = """
            SELECT value FROM agent_memory
            WHERE key = :key 
            AND (expires_at IS NULL OR expires_at > NOW())
        """
        
        try:
            with self._get_session() as session:
                result = session.execute(text(query), {"key": key})
                row = result.fetchone()
                
                if row:
                    val = row[0]
                    if isinstance(val, (str, bytes, bytearray)):
                        try:
                            return json.loads(val)
                        except:
                            return val
                    return val
        except Exception as e:
            logger.warning(f"[MEMORY] DB Recall failed: {e}")

        # 2. Fallback to Markdown Source of Truth
        logger.debug(f"[MEMORY] Cache miss for {key}. Checking Markdown...")
        entry = self.md_storage.find_by_key(key)
        if entry:
            logger.info(f"[MEMORY] Recovered {key} from Markdown storage.")
            return entry.value
            
        return None
            
    async def forget(self, key: str) -> bool:
        """Delete a memory by key"""
        query = "DELETE FROM agent_memory WHERE key = :key"
        
        try:
            with self._get_session() as session:
                session.execute(text(query), {"key": key})
                session.commit()
                return True
        except Exception as e:
            logger.error(f"[MEMORY] Failed to forget memory: {e}")
            return False
            
    async def search(
        self,
        category: Optional[MemoryCategory] = None,
        min_importance: float = 0.0,
        limit: int = 50
    ) -> list[MemoryEntry]:
        """
        Search memories by category and importance.
        
        Args:
            category: Filter by category (None = all)
            min_importance: Minimum importance threshold
            limit: Max results
            
        Returns:
            List of matching MemoryEntry objects
        """
        query = """
            SELECT id, key, value, category, importance, created_at, expires_at
            FROM agent_memory
            WHERE importance >= :min_importance
            AND (expires_at IS NULL OR expires_at > NOW())
        """
        params = {"min_importance": min_importance, "limit": limit}
        
        if category:
            query += " AND category = :category"
            params["category"] = category.value
            
        query += " ORDER BY importance DESC, created_at DESC LIMIT :limit"
        
        try:
            with self._get_session() as session:
                result = session.execute(text(query), params)
                rows = result.fetchall()
                
                def parse_json(val):
                    if isinstance(val, (str, bytes, bytearray)):
                        try:
                            return json.loads(val)
                        except:
                            return val
                    return val

                return [
                    MemoryEntry(
                        id=str(row[0]),
                        key=row[1],
                        value=parse_json(row[2]),
                        category=MemoryCategory(row[3]),
                        importance=row[4],
                        created_at=row[5],
                        expires_at=row[6]
                    )
                    for row in rows
                ]
        except Exception as e:
            logger.error(f"[MEMORY] Search failed: {e}")
            return []

    async def search_semantic(
        self,
        query_text: str,
        category: Optional[MemoryCategory] = None,
        limit: int = 5,
        threshold: Optional[float] = None,
        query_vector: Optional[list[float]] = None # Optimization: Reuse vector
    ) -> list[MemoryEntry]:
        """
        Perform semantic similarity search using pgvector.
        Args:
            threshold: Max cosine distance (lower is more similar). e.g., 0.5
        """
        from utils.embeddings import get_embedding_engine
        
        if query_vector is None:
            engine = get_embedding_engine()
            t_embed_start = datetime.now()
            query_vector = await engine.get_embedding(query_text)
            t_embed_end = datetime.now()
            logger.debug(f"[PERF] Embedding generation took: {(t_embed_end - t_embed_start).total_seconds():.3f}s")
        
        if not query_vector:
            # Fallback to normal search if embedding fails
            logger.warning("[MEMORY] Semantic search fallback to keyword search")
            return await self.search(category=category, limit=limit)

        query = """
            SELECT id, key, value, category, importance, created_at, expires_at,
                   (embedding <=> :query_vector) AS distance
            FROM agent_memory
            WHERE (expires_at IS NULL OR expires_at > NOW())
            AND embedding IS NOT NULL
        """
        params = {"query_vector": str(query_vector), "limit": limit}
        
        if category:
            query += " AND category = :category"
            params["category"] = category.value
            
        if threshold is not None:
             # Filter by distance (Requires pgvector <-> operator)
            query += " AND (embedding <=> :query_vector) < :threshold"
            params["threshold"] = threshold
            
        # Use cosine distance (<=>) for similarity
        query += " ORDER BY embedding <=> :query_vector ASC LIMIT :limit"
        
        try:
            with self._get_session() as session:
                t_sql_start = datetime.now()
                result = session.execute(text(query), params)
                rows = result.fetchall()
                t_sql_end = datetime.now()
                logger.debug(f"[PERF] SQL Vector Query took: {(t_sql_end - t_sql_start).total_seconds():.3f}s")
                
                def parse_json(val):
                    if isinstance(val, (str, bytes, bytearray)):
                        try: return json.loads(val)
                        except: return val
                    return val

                return [
                    MemoryEntry(
                        id=str(row[0]), key=row[1], value=parse_json(row[2]),
                        category=MemoryCategory(row[3]), importance=row[4],
                        created_at=row[5], expires_at=row[6],
                        score=float(row[7]) if row[7] is not None else 0.0
                    )
                    for row in rows
                ]
        except Exception as e:
            logger.error(f"[MEMORY] Semantic search failed: {e}")
            return []
            
    async def rrf_search(
        self,
        query_text: str,
        categories: list[MemoryCategory] = None,
        limit: int = 10,
        k: int = 60
    ) -> list[MemoryEntry]:
        """
        Reciprocal Rank Fusion (RRF) Algorithm:
        Merges results from multiple search streams (Semantic, Keyword, Importance).
        
        Score(d) = sum(1 / (k + rank(d, r))) for r in runs
        """
        from utils.embeddings import get_embedding_engine
        engine = get_embedding_engine()
        query_vector = await engine.get_embedding(query_text)
        
        # 1. Semantic Stream
        semantic_results = await self.search_semantic(query_text, limit=limit*2, query_vector=query_vector)
        
        # 2. Keyword Stream (entity-based)
        keywords = [w for w in re.findall(r'\w+', query_text.lower()) if len(w) > 3]
        keyword_results = []
        if keywords:
            for word in keywords[:3]:
                keyword_results.extend(await self.search(limit=limit))
        
        # Merge logic
        scores = {}
        entries = {}
        
        def update_scores(results, weight=1.0):
            for rank, entry in enumerate(results, 1):
                if entry.id not in scores:
                    scores[entry.id] = 0.0
                    entries[entry.id] = entry
                scores[entry.id] += weight * (1.0 / (k + rank))

        update_scores(semantic_results, weight=1.5) # Prefer semantic
        update_scores(keyword_results, weight=1.0)
        
        # Sort by RRF score
        sorted_ids = sorted(scores.keys(), key=lambda x: scores[x], reverse=True)
        return [entries[mid] for mid in sorted_ids[:limit]]

    async def deep_recall(
        self, 
        query_text: str, 
        limit: int = 15,
        query_vector: Optional[list[float]] = None
    ) -> list[MemoryEntry]:
        """
        Phase 5: Critical Markdown Memory Recall.
        Completely bypasses slow Vector Search and strictly uses fast Regex/Keyword Markdown indexing.
        """
        import re
        
        # 1. Clean keywords from query text
        # Filter out common stop words to keep search hyper-focused
        stop_words = {'có', 'không', 'với', 'cho', 'này', 'là', 'những', 'của', 'the', 'and', 'with', 'what'}
        keywords = [w.lower() for w in re.findall(r'\w+', query_text) if len(w) > 3 and w.lower() not in stop_words]
        
        if not keywords:
            logger.debug("[MEMORY] Deep Recall failed: Too few keywords.")
            return []
            
        logger.debug(f"[MEMORY] Fast Markdown Recall for keywords: {keywords}")
        
        # 2. Perform lightning-fast Markdown file scan
        md_matches = self.md_storage.search_by_keywords(keywords, limit=limit)
        
        results = []
        for entry in md_matches:
            # Convert MarkdownMemoryEntry back to SQL-like MemoryEntry for downstream compatibility
            cat_enum = MemoryCategory.CONTEXT
            try:
                cat_enum = MemoryCategory(entry.category)
            except:
                pass
                
            results.append(MemoryEntry(
                id=f"md:{entry.key}",
                key=entry.key,
                value=entry.value,
                category=cat_enum,
                importance=entry.importance,
                created_at=datetime.fromisoformat(entry.created_at) if entry.created_at else datetime.utcnow()
            ))
            
        logger.info(f"[MEMORY] Markdown Recall found {len(results)} matches.")
        return results

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
        
        # Get recent actions
        actions_key_prefix = f"user_action:{user_id}:"
        query = """
            SELECT key, value, created_at FROM agent_memory
            WHERE key LIKE :prefix
            ORDER BY created_at DESC
            LIMIT 10
        """
        
        recent_actions = []
        try:
            with self._get_session() as session:
                result = session.execute(text(query), {"prefix": f"{actions_key_prefix}%"})
                for row in result.fetchall():
                    recent_actions.append({
                        "action": json.loads(row[1]),
                        "timestamp": row[2].isoformat()
                    })
        except Exception as e:
            logger.warning(f"[MEMORY] Failed to get user history: {e}")
            
        return {
            "user_id": user_id,
            "warning_count": warnings,
            "risk_score": risk_score,
            "recent_actions": recent_actions,
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
        """Get decision history from agent_memory"""
        query = """
            SELECT key, value, created_at
            FROM agent_memory
            WHERE category = :category
        """
        params = {"category": MemoryCategory.DECISION.value, "limit": limit}
        
        if target_id:
            query += " AND value->>'target_id' = :target_id"
            params["target_id"] = target_id
            
        if action:
            query += " AND value->>'action' = :action"
            params["action"] = action
            
        query += " ORDER BY created_at DESC LIMIT :limit"
        
        try:
            with self._get_session() as session:
                result = session.execute(text(query), params)
                decisions = []
                for row in result.fetchall():
                    val = row[1]
                    if isinstance(val, str):
                        try:
                            val = json.loads(val)
                        except:
                            pass
                    
                    if isinstance(val, dict):
                        val["id"] = row[0]
                        if "created_at" not in val:
                            val["created_at"] = row[2].isoformat()
                        decisions.append(val)
                return decisions
        except Exception as e:
            logger.error(f"[MEMORY] Failed to get decision history: {e}")
            return []
            
            
    async def get_daily_actions(self, hours: int = 24) -> list[dict]:
        """Get all decisions from memory in the last N hours"""
        query = """
            SELECT value
            FROM agent_memory
            WHERE category = :category
            AND created_at >= NOW() - INTERVAL '1 hour' * :hours
            ORDER BY created_at DESC
        """
        try:
            with self._get_session() as session:
                result = session.execute(text(query), {
                    "category": MemoryCategory.DECISION.value,
                    "hours": hours
                })
                decisions = []
                for row in result.fetchall():
                    val = row[0]
                    if isinstance(val, str):
                        try:
                            val = json.loads(val)
                        except:
                            pass
                    if isinstance(val, dict):
                        decisions.append(val)
                return decisions
        except Exception as e:
            logger.error(f"[MEMORY] Failed to get daily actions: {e}")
            return []
            
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
        Retrieve recent chat history for a session.
        Checks DB cache first, then falls back to Markdown session file.
        """
        prefix = f"chat:{chat_id}:"
        query = """
            SELECT value FROM agent_memory
            WHERE key LIKE :prefix
            AND (expires_at IS NULL OR expires_at > NOW())
            ORDER BY created_at DESC
            LIMIT :limit
        """
        try:
            with self._get_session() as session:
                result = session.execute(text(query), {"prefix": f"{prefix}%", "limit": limit})
                
                def parse_json(val):
                    if isinstance(val, (str, bytes, bytearray)):
                        try:
                            return json.loads(val)
                        except:
                            return val
                    return val
                
                rows = result.fetchall()
                if rows:
                    # Reverse to get chronological order (oldest to newest)
                    history = [parse_json(row[0]) for row in rows]
                    return history[::-1]
        except Exception as e:
            logger.warning(f"[MEMORY] DB History retrieval failed: {e}")

        # 2. Fallback to Markdown Source of Truth
        logger.debug(f"[MEMORY] History cache miss for {chat_id}. Checking Markdown...")
        file_path = self.md_storage._get_file_path("context", f"chat:{chat_id}:now")
        entries = self.md_storage.load_all_from_file(file_path)
        if entries:
            # Sort by created_at and take last N
            entries.sort(key=lambda x: x.created_at)
            history = [e.value for e in entries[-limit:]]
            logger.info(f"[MEMORY] Recovered {len(history)} messages from Markdown file.")
            return history
            
        return []
        
    # ==========================================
    # MAINTENANCE
    # ==========================================
    
    async def cleanup_expired(self) -> int:
        """Remove expired memories"""
        query = "DELETE FROM agent_memory WHERE expires_at < NOW()"
        
        try:
            with self._get_session() as session:
                result = session.execute(text(query))
                session.commit()
                deleted = result.rowcount
                
                if deleted > 0:
                    logger.info(f"[MEMORY] Cleaned up {deleted} expired memories")
                return deleted
        except Exception as e:
            logger.error(f"[MEMORY] Cleanup failed: {e}")
            return 0
            
    async def get_stats(self) -> dict:
        """Get memory statistics"""
        query = """
            SELECT 
                category,
                COUNT(*) as count,
                AVG(importance) as avg_importance
            FROM agent_memory
            WHERE expires_at IS NULL OR expires_at > NOW()
            GROUP BY category
        """
        
        try:
            with self._get_session() as session:
                result = session.execute(text(query))
                categories = {
                    row[0]: {"count": row[1], "avg_importance": float(row[2]) if row[2] else 0}
                    for row in result.fetchall()
                }
                
                # Get decision count from memory
                decision_result = session.execute(text(
                    "SELECT COUNT(*) FROM agent_memory WHERE category = :category"
                ), {"category": MemoryCategory.DECISION.value})
                decision_count = decision_result.fetchone()[0]
                
                return {
                    "memory_categories": categories,
                    "total_memories": sum(c["count"] for c in categories.values()),
                    "total_decisions": decision_count
                }
        except Exception as e:
            logger.error(f"[MEMORY] Failed to get stats: {e}")
            return {}


# Singleton instance
_memory_instance: Optional[PersistentMemory] = None


def get_memory(base_path: str = "data/storage") -> PersistentMemory:
    """Get the global memory instance, or create one with specific paths"""
    global _memory_instance
    if _memory_instance is None:
        _memory_instance = PersistentMemory(base_path=base_path)
    return _memory_instance
