"""
SpatialAwareness — Agent's perception of its environment.

Tracks WHO is around, WHAT they're discussing, and decides
whether the agent should engage. Designed to be imported by
any layer (handler, brain, connector) without circular deps.
"""
import os
import json
import re
from datetime import datetime
from typing import Dict, List, Optional
from dataclasses import dataclass, field, asdict

from utils.logger import get_logger


logger = get_logger()


@dataclass
class Participant:
    """A known entity in the agent's social field."""
    username: str
    display_name: str
    is_bot: bool
    first_seen: str
    last_seen: str
    chat_ids: set = field(default_factory=set)
    message_count: int = 0

    def to_dict(self) -> dict:
        d = asdict(self)
        d["chat_ids"] = list(self.chat_ids)
        return d

    @classmethod
    def from_dict(cls, data: dict) -> 'Participant':
        chat_ids = set(data.pop("chat_ids", []))
        return cls(chat_ids=chat_ids, **data)


class ContextWindow:
    """
    Sliding window of recent group activity (in-memory only).
    Provides summarized context for brain decisions.
    """

    def __init__(self, max_per_chat: int = 30):
        self._buffers: Dict[str, List[dict]] = {}
        self._max = max_per_chat

    def push(self, chat_id: str, sender: str, text: str):
        cid = str(chat_id)
        if cid not in self._buffers:
            self._buffers[cid] = []

        self._buffers[cid].append({
            "sender": sender,
            "text": text[:250],
            "ts": datetime.utcnow().timestamp(),
        })

        if len(self._buffers[cid]) > self._max:
            self._buffers[cid] = self._buffers[cid][-self._max:]

    def recent(self, chat_id: str, limit: int = 10) -> List[dict]:
        return self._buffers.get(str(chat_id), [])[-limit:]

    def topic_keywords(self, chat_id: str, top_n: int = 8) -> List[str]:
        """Extract dominant keywords from recent messages (fast frequency)."""
        msgs = self.recent(chat_id, limit=20)
        if not msgs:
            return []
        from collections import Counter
        words = Counter()
        stop = {"the", "a", "an", "is", "are", "was", "to", "of", "in", "for",
                "and", "on", "it", "i", "you", "that", "this", "with", "but",
                "là", "của", "và", "có", "không", "được", "cho", "đã", "từ"}
        for m in msgs:
            for w in m["text"].lower().split():
                # Strip punctuation
                w = re.sub(r'[.,:!?)]+', '', w)
                if len(w) > 2 and w not in stop:
                    words[w] += 1
        return [w for w, _ in words.most_common(top_n)]


class SpatialAwareness:
    """
    Agent's perception of its surroundings.
    Tracks: WHO is here, WHAT they're discussing, HOW the agent relates.

    Designed as a standalone module — zero dependency on channel/handler.
    """

    # Domain keywords for relevance scoring
    DOMAIN_KEYWORDS = frozenset([
        "database", "music", "track", "artist", "nivasound", "niva",
        "server", "system", "memory", "agent", "bot", "ai",
        "security", "audit", "anomaly", "report", "data",
        "brain", "sentry", "patrol", "log", "error",
    ])

    def __init__(self, base_path: str = "data/storage"):
        self._participants: Dict[str, Participant] = {}
        self.context = ContextWindow()
        self.base_path = base_path
        
    async def initialize(self):
        """Load participants from persistent Vector memory."""
        try:
            from memory.persistent import get_memory, MemoryCategory
            memory = get_memory()
            
            # Use specific category for participant profiles
            # In Vector mode, we search for entries with category USER_HISTORY and prefix 'participant:'
            results = await memory.search("", category=MemoryCategory.USER_HISTORY, limit=200)
            for entry in results:
                if entry.key.startswith("participant:"):
                    p = Participant.from_dict(entry.value)
                    self._participants[p.username.lower()] = p
            
            logger.info(f"[AWARENESS] Loaded {len(self._participants)} participants from VectorEngine")
        except Exception as e:
            logger.warning(f"[AWARENESS] Failed to load participants: {e}")

    # ── Participant tracking ──────────────────────────────────

    async def observe(self, username: str, display_name: str,
                is_bot: bool, chat_id: str, text: str = ""):
        """Record seeing a participant + buffer their message + persist."""
        if not username:
            return
        key = username.lower()
        now = datetime.utcnow().isoformat()

        is_new = key not in self._participants
        if is_new:
            self._participants[key] = Participant(
                username=username,
                display_name=display_name,
                is_bot=is_bot,
                first_seen=now,
                last_seen=now,
            )
        p = self._participants[key]
        p.last_seen = now
        p.chat_ids.add(str(chat_id))
        p.message_count += 1

        if text:
            self.context.push(chat_id, username, text)
            
        # Persist every 5 messages or if new
        if is_new or p.message_count % 5 == 0:
            try:
                from memory.persistent import get_memory, MemoryCategory
                memory = get_memory()
                await memory.remember(
                    key=f"participant:{key}",
                    value=p.to_dict(),
                    category=MemoryCategory.USER_HISTORY,
                    importance=0.2
                )
            except Exception as e:
                logger.debug(f"[AWARENESS] Failed to persist participant {username}: {e}")

    def get_peers(self, *, chat_id: str = None,
                  exclude: str = None) -> List[Participant]:
        """Return known participants, optionally filtered."""
        out = []
        for key, p in self._participants.items():
            if exclude and key == exclude.lower():
                continue
            if chat_id and str(chat_id) not in p.chat_ids:
                continue
            out.append(p)
        return out

    def get_peer_usernames(self, **kw) -> List[str]:
        return [p.username for p in self.get_peers(**kw)]


    # ── Helpers ────────────────────────────────────────────────

    def snapshot(self, chat_id: str = None) -> dict:
        """Return a compact snapshot for the brain context."""
        peers = self.get_peers(chat_id=chat_id)
        return {
            "peer_count": len(peers),
            "peers": [{"u": p.username, "bot": p.is_bot,
                        "msgs": p.message_count} for p in peers[:15]],
            "topics": self.context.topic_keywords(chat_id) if chat_id else [],
            "recent": self.context.recent(chat_id, 5) if chat_id else [],
        }
