"""
Short-Term Memory
Rolling window memory for recent observations and actions
"""
from datetime import datetime, timedelta
from typing import Any, Optional, Tuple
from dataclasses import dataclass, field
from collections import deque
import numpy as np

from config.settings import settings


@dataclass
class MemoryEntry:
    """A single entry in short-term memory"""
    timestamp: datetime
    category: str  # observation, thought, action, result
    content: Any
    metadata: dict = field(default_factory=dict)
    
    def is_expired(self, max_age_hours: int) -> bool:
        """Check if this memory entry has expired"""
        age = datetime.utcnow() - self.timestamp
        return age > timedelta(hours=max_age_hours)


class ShortTermMemory:
    """
    Manages the agent's short-term memory.
    Uses a rolling window approach to maintain recent context.
    """
    
    def __init__(self, max_entries: int = 1000):
        self.max_entries = max_entries
        self.rolling_window_hours = settings.rolling_window_hours
        
        # Separate queues for different types of memories
        self._observations: deque[MemoryEntry] = deque(maxlen=max_entries)
        self._thoughts: deque[MemoryEntry] = deque(maxlen=500)
        self._actions: deque[MemoryEntry] = deque(maxlen=200)
        self._actions: deque[MemoryEntry] = deque(maxlen=200)
        self._results: deque[MemoryEntry] = deque(maxlen=200)
        
        # Vector QA Cache (The "Short-Term" caching user requested)
        # List of dicts: {'vector': np.array, 'response': str, 'timestamp': float, 'query_text': str}
        self._cache: list[dict] = [] 
        self._cache_ttl = 3600 # 1 hour cache
        self._similarity_threshold = 0.92 # High threshold for near-duplicates
        
        # Track actions taken on specific targets (for cooldown)
        self._action_history: dict[str, list[datetime]] = {}
    
    def add_observation(self, content: Any, metadata: dict = None):
        """Record an observation from the environment"""
        entry = MemoryEntry(
            timestamp=datetime.utcnow(),
            category="observation",
            content=content,
            metadata=metadata or {}
        )
        self._observations.append(entry)
    
    def add_thought(self, content: str, metadata: dict = None):
        """Record an internal thought/reasoning"""
        entry = MemoryEntry(
            timestamp=datetime.utcnow(),
            category="thought",
            content=content,
            metadata=metadata or {}
        )
        self._thoughts.append(entry)
    
    def add_action(self, action_type: str, target_id: str, details: dict = None):
        """Record an action taken"""
        entry = MemoryEntry(
            timestamp=datetime.utcnow(),
            category="action",
            content={
                "action_type": action_type,
                "target_id": target_id,
                "details": details or {}
            },
            metadata={"target_id": target_id}
        )
        self._actions.append(entry)
        
        # Track for cooldown
        key = f"{action_type}:{target_id}"
        if key not in self._action_history:
            self._action_history[key] = []
        self._action_history[key].append(datetime.utcnow())
    
    def add_result(self, action_id: str, success: bool, details: Any = None):
        """Record the result of an action"""
        entry = MemoryEntry(
            timestamp=datetime.utcnow(),
            category="result",
            content={
                "action_id": action_id,
                "success": success,
                "details": details
            }
        )
        self._results.append(entry)
    
    def get_recent_observations(self, hours: int = None) -> list[MemoryEntry]:
        """Get observations within the time window"""
        hours = hours or self.rolling_window_hours
        cutoff = datetime.utcnow() - timedelta(hours=hours)
        return [o for o in self._observations if o.timestamp >= cutoff]
    
    def get_recent_thoughts(self, count: int = 10) -> list[MemoryEntry]:
        """Get the most recent thoughts"""
        return list(self._thoughts)[-count:]
    
    def get_recent_actions(self, hours: int = 1) -> list[MemoryEntry]:
        """Get actions taken within the time window"""
        cutoff = datetime.utcnow() - timedelta(hours=hours)
        return [a for a in self._actions if a.timestamp >= cutoff]
    
    def get_action_count_for_target(
        self,
        action_type: str,
        target_id: str,
        minutes: int = 60
    ) -> int:
        """Count how many times an action was taken on a target"""
        key = f"{action_type}:{target_id}"
        if key not in self._action_history:
            return 0
        
        cutoff = datetime.utcnow() - timedelta(minutes=minutes)
        recent = [t for t in self._action_history[key] if t >= cutoff]
        return len(recent)
    
    def is_on_cooldown(
        self,
        action_type: str,
        target_id: str,
        cooldown_minutes: int
    ) -> bool:
        """Check if an action on a target is on cooldown"""
        key = f"{action_type}:{target_id}"
        if key not in self._action_history:
            return False
        
        if not self._action_history[key]:
            return False
        
        last_action = max(self._action_history[key])
        elapsed = datetime.utcnow() - last_action
        return elapsed < timedelta(minutes=cooldown_minutes)
    
    def get_summary(self) -> dict:
        """Get a summary of current memory state"""
        return {
            "observations_count": len(self._observations),
            "thoughts_count": len(self._thoughts),
            "actions_count": len(self._actions),
            "results_count": len(self._results),
            "tracked_targets": len(self._action_history)
        }
    
    def cleanup_expired(self):
        """Remove expired entries from memory"""
        cutoff = datetime.utcnow() - timedelta(hours=self.rolling_window_hours * 2)
        
        # Clean up action history
        for key in list(self._action_history.keys()):
            self._action_history[key] = [
                t for t in self._action_history[key] if t >= cutoff
            ]
            if not self._action_history[key]:
                del self._action_history[key]

    def clear(self):
        """Clear all short-term memory entries"""
        self._observations.clear()
        self._thoughts.clear()
        self._actions.clear()
        self._results.clear()
        self._action_history.clear()
        self._cache.clear()

    def get_cache(self, query_vector: list[float]) -> Optional[Any]:
        """Retrieve a cached response (text or dict) using vector similarity"""
        if not query_vector or not self._cache: return None
        
        query_vec = np.array(query_vector)
        norm_query = np.linalg.norm(query_vec)
        if norm_query == 0: return None
        
        best_resp = None
        best_score = -1.0
        now = datetime.utcnow().timestamp()
        
        # Cleanup expired first
        self._cache = [e for e in self._cache if (now - e['timestamp']) < self._cache_ttl]
        
        for entry in self._cache:
            cand_vec = entry['vector']
            norm_cand = np.linalg.norm(cand_vec)
            if norm_cand == 0: continue
            
            # Cosine Similarity
            score = np.dot(query_vec, cand_vec) / (norm_query * norm_cand)
            
            if score > best_score:
                best_score = score
                best_resp = entry['response']
                
        if best_score >= self._similarity_threshold:
            return best_resp
            
        return None

    def set_cache(self, query_vector: list[float], response: Any, query_text: str = ""):
        """Cache a response (text or dict) locally with vector"""
        if not query_vector or not response: return
        
        self._cache.append({
            'vector': np.array(query_vector),
            'response': response,
            'timestamp': datetime.utcnow().timestamp(),
            'query_text': query_text
        })
        # Limit cache size
        if len(self._cache) > 100:
            self._cache.pop(0)
