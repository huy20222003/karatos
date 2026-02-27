import os
import yaml
import json
from datetime import datetime
from typing import Any, List, Optional, Dict
from dataclasses import dataclass, asdict

from utils.logger import get_logger
from utils.crypto import decrypt_file, write_encrypted
from utils.helpers import safe_json_parse, safe_json_dumps, resolve_path

logger = get_logger()

class MemoryIndex:
    """
    Lightweight index for fast key-to-file mapping.
    Avoids full directory scans for specific key lookups.
    """
    def __init__(self, index_path: str):
        self.index_path = index_path
        self.data: Dict[str, Dict[str, str]] = {}
        self.load()

    def load(self):
        if os.path.exists(self.index_path):
            self.data = safe_json_parse(open(self.index_path, "r", encoding="utf-8").read(), default={})

    def save(self):
        try:
            os.makedirs(os.path.dirname(self.index_path), exist_ok=True)
            with open(self.index_path, "w", encoding="utf-8") as f:
                f.write(safe_json_dumps(self.data, indent=2))
        except Exception as e:
            logger.error(f"[MEMORY_INDEX] Save failed: {e}")

    def update(self, key: str, file_path: str, category: str):
        self.data[key] = {
            "file": file_path,
            "category": category,
            "updated_at": datetime.utcnow().isoformat()
        }
        self.save()

    def get(self, key: str) -> Optional[Dict[str, str]]:
        return self.data.get(key)

@dataclass
class MarkdownMemoryEntry:
    key: str
    category: str
    importance: float
    created_at: str
    value: Any
    expires_at: Optional[str] = None

class MarkdownMemory:
    """
    Markdown-based storage for Agent Memory.
    Organizes memories into categorized .md files with YAML frontmatter.
    """
    
    def __init__(self, base_path: str = "data/storage"):
        self.base_path = base_path
        self._ensure_directories()
        
        # Initialize Index
        index_file = os.path.join(self.base_path, "sys", "cache", "memory_index.json")
        self.index = MemoryIndex(index_file)

    def _ensure_directories(self):
        """Create storage hierarchy matching all 18 MemoryCategory values."""
        os.makedirs(self.base_path, exist_ok=True)
        
        # ═══ EPISODIC MEMORY ═══
        os.makedirs(os.path.join(self.base_path, "memory", "sessions"), exist_ok=True)      # CONTEXT
        os.makedirs(os.path.join(self.base_path, "memory", "experiences"), exist_ok=True)    # EXPERIENCE
        os.makedirs(os.path.join(self.base_path, "memory", "decisions"), exist_ok=True)      # DECISION
        os.makedirs(os.path.join(self.base_path, "memory", "emotions"), exist_ok=True)       # EMOTION
        
        # ═══ SEMANTIC MEMORY ═══
        os.makedirs(os.path.join(self.base_path, "memory", "learnings"), exist_ok=True)      # LEARNING
        os.makedirs(os.path.join(self.base_path, "memory", "facts"), exist_ok=True)          # FACT
        os.makedirs(os.path.join(self.base_path, "memory", "procedures"), exist_ok=True)     # PROCEDURAL
        
        # ═══ IDENTITY MEMORY ═══
        os.makedirs(os.path.join(self.base_path, "profiles", "identity"), exist_ok=True)     # PERSONA
        os.makedirs(os.path.join(self.base_path, "memory", "reflections"), exist_ok=True)    # REFLECTION
        os.makedirs(os.path.join(self.base_path, "memory", "beliefs"), exist_ok=True)        # BELIEF
        
        # ═══ SOCIAL MEMORY ═══
        os.makedirs(os.path.join(self.base_path, "profiles", "users"), exist_ok=True)        # USER_PROFILE + USER_HISTORY
        os.makedirs(os.path.join(self.base_path, "profiles", "relationships"), exist_ok=True) # RELATIONSHIP
        os.makedirs(os.path.join(self.base_path, "profiles", "dynamics"), exist_ok=True)     # SENTIMENT
        
        # ═══ EXECUTIVE MEMORY ═══
        os.makedirs(os.path.join(self.base_path, "memory", "goals"), exist_ok=True)          # GOAL
        os.makedirs(os.path.join(self.base_path, "memory", "habits"), exist_ok=True)         # HABIT
        
        # ═══ SYSTEM MEMORY ═══
        os.makedirs(os.path.join(self.base_path, "memory", "system"), exist_ok=True)         # SYSTEM
        os.makedirs(os.path.join(self.base_path, "memory", "a2a"), exist_ok=True)            # A2A
        os.makedirs(os.path.join(self.base_path, "sys", "metadata"), exist_ok=True)          # METADATA
        
        # ═══ INFRASTRUCTURE ═══
        os.makedirs(os.path.join(self.base_path, "sys", "cache"), exist_ok=True)
        os.makedirs(os.path.join(self.base_path, "sys", "intuition"), exist_ok=True)
        os.makedirs(os.path.join(self.base_path, "vault"), exist_ok=True)

    def _get_file_path(self, category: str, key: str) -> str:
        """Maps every MemoryCategory to a dedicated storage file. No general_memory.md fallback."""
        category = category.upper()

        # ═══ EPISODIC ═══
        if category == "CONTEXT" or "chat:" in key:
            if "chat:" in key:
                parts = key.split(":")
                if len(parts) > 1:
                    chat_id = parts[1]
                    return os.path.join(self.base_path, "memory", "sessions", f"{chat_id}.md")
            return os.path.join(self.base_path, "memory", "sessions", "general.md")

        if category == "EXPERIENCE":
            return os.path.join(self.base_path, "memory", "experiences", "history.md")

        if category == "DECISION" or "dec:" in key:
            return os.path.join(self.base_path, "memory", "decisions", "history.md")

        if category == "EMOTION":
            return os.path.join(self.base_path, "memory", "emotions", "chronicle.md")

        # ═══ SEMANTIC ═══
        if category == "LEARNING":
            return os.path.join(self.base_path, "memory", "learnings", "knowledge.md")

        if category == "FACT":
            return os.path.join(self.base_path, "memory", "facts", "world.md")

        if category == "PROCEDURAL":
            return os.path.join(self.base_path, "memory", "procedures", "workflows.md")

        # ═══ IDENTITY ═══
        if category == "PERSONA":
            return os.path.join(self.base_path, "profiles", "identity", "persona.md")

        if category == "REFLECTION":
            return os.path.join(self.base_path, "memory", "reflections", "lessons.md")

        if category == "BELIEF":
            return os.path.join(self.base_path, "memory", "beliefs", "principles.md")

        # ═══ SOCIAL ═══
        if category == "USER_PROFILE":
            return os.path.join(self.base_path, "profiles", "users", "preferences.md")

        if category == "USER_HISTORY" or "user_" in key:
            return os.path.join(self.base_path, "profiles", "users", "history.md")

        if category == "RELATIONSHIP":
            return os.path.join(self.base_path, "profiles", "relationships", "bonds.md")

        if category == "SENTIMENT":
            return os.path.join(self.base_path, "profiles", "dynamics", "moods.md")

        # ═══ EXECUTIVE ═══
        if category == "GOAL":
            return os.path.join(self.base_path, "memory", "goals", "objectives.md")

        if category == "HABIT":
            return os.path.join(self.base_path, "memory", "habits", "patterns.md")

        # ═══ SYSTEM ═══
        if category == "SYSTEM":
            return os.path.join(self.base_path, "memory", "system", "state.md")

        if category == "METADATA":
            return os.path.join(self.base_path, "sys", "metadata", "technical.md")

        if category == "A2A":
            return os.path.join(self.base_path, "memory", "a2a", "messages.md")

        if category == "INTUITION":
            return os.path.join(self.base_path, "sys", "intuition", "insights.md")

        if category == "VAULT":
            return os.path.join(self.base_path, "vault", "secrets.md")

        # Fallback (should rarely be reached now)
        return os.path.join(self.base_path, "memory", "general_memory.md")

    def append(self, entry: MarkdownMemoryEntry):
        """Append a memory entry to its corresponding markdown file"""
        file_path = self._get_file_path(entry.category, entry.key)
        
        # Prepare content
        frontmatter = {
            "key": entry.key,
            "category": entry.category,
            "importance": entry.importance,
            "created_at": entry.created_at,
        }
        if entry.expires_at:
            frontmatter["expires_at"] = entry.expires_at

        # Serialize value (pretty if dict/list)
        if isinstance(entry.value, (dict, list)):
            content_body = json.dumps(entry.value, indent=2, ensure_ascii=False)
        else:
            content_body = str(entry.value)

        # Build block
        # USE UNIQUE DELIMITER TO PREVENT CONTENT BREAKING PARSER
        markdown_block = f"""
--- # MEMORY_ENTRY # ---
{yaml.dump(frontmatter, sort_keys=False).strip()}
---
{content_body}

"""
        try:
            write_encrypted(file_path, markdown_block, mode="a")
            # Update Index for O(1) retrieval
            self.index.update(entry.key, file_path, entry.category)
            logger.debug(f"[MD_MEMORY] Appended (encrypted) to {file_path}")
        except Exception as e:
            logger.error(f"[MD_MEMORY] Write failed: {e}")

    def load_all_from_file(self, file_path: str, limit_last: Optional[int] = None) -> List[MarkdownMemoryEntry]:
        """Parses a markdown file and returns entries. Supports tail loading."""
        if not os.path.exists(file_path):
            return []
            
        entries = []
        try:
            content = decrypt_file(file_path)
            if not content:
                return []
                
            # Split by unique delimiter first
            entries_raw = content.split("--- # MEMORY_ENTRY # ---")
            
            # OPTIMIZATION: If limit_last is set, only process the last N entries
            if limit_last and len(entries_raw) > limit_last + 1:
                entries_raw = entries_raw[-(limit_last + 1):]
            
            for entry_raw in entries_raw:
                entry_raw = entry_raw.strip()
                if not entry_raw: continue
                
                try:
                    # Within each entry, split by frontmatter end delimiter
                    if "---" not in entry_raw:
                        # Fallback for old format if detected
                        parts = entry_raw.split("---")
                        if len(parts) >= 2:
                            meta_raw = parts[0].strip()
                            body_raw = "---".join(parts[1:]).strip()
                        else:
                            continue
                    else:
                        parts = entry_raw.split("---", 1)
                        meta_raw = parts[0].strip()
                        body_raw = parts[1].strip() if len(parts) > 1 else ""
                    
                    try:
                        meta = yaml.safe_load(meta_raw)
                    except yaml.YAMLError as ye:
                        logger.warning(f"[MD_MEMORY] YAML Error in {file_path}: {ye}")
                        continue

                    if not meta or "key" not in meta:
                        continue
                        
                    # Parse value back from JSON if possible
                    try:
                        value = json.loads(body_raw)
                    except:
                        value = body_raw
                        
                    entries.append(MarkdownMemoryEntry(
                        key=meta["key"],
                        category=meta["category"],
                        importance=meta["importance"],
                        created_at=meta["created_at"],
                        value=value,
                        expires_at=meta.get("expires_at")
                    ))
                except Exception as parse_err:
                    logger.warning(f"[MD_MEMORY] Entry parse error in {file_path}: {parse_err}")
                
            return entries
        except Exception as e:
            logger.error(f"[MD_MEMORY] Load failed for {file_path}: {e}")
            return []

    def find_by_key(self, key: str) -> Optional[MarkdownMemoryEntry]:
        """Fast O(1) key lookup using index."""
        idx_info = self.index.get(key)
        if idx_info:
            file_path = idx_info["file"]
            entries = self.load_all_from_file(file_path)
            for entry in entries:
                if entry.key == key:
                    return entry
                    
        # Fallback to slow scan if not in index (e.g. legacy data)
        categories = [
            "context", "user_history", "decision", "learning", "experience",
            "reflection", "fact", "procedural", "persona", "belief",
            "user_profile", "relationship", "sentiment", "goal", "habit",
            "system", "metadata", "a2a", "emotion"
        ]
        for cat in categories:
            file_path = self._get_file_path(cat, key)
            if os.path.exists(file_path):
                entries = self.load_all_from_file(file_path)
                for entry in entries:
                    if entry.key == key:
                        # Auto-heal index
                        self.index.update(key, file_path, cat)
                        return entry
        return None

    def search_by_keywords(self, keywords: List[str], limit: int = 15) -> List[MarkdownMemoryEntry]:
        """
        BM25 Ranked Memory Retrieval (Okapi Best Match 25).
        
        Replaces naive keyword counting with industry-standard information retrieval:
        - Term Frequency (TF): Diminishing returns for repeated keywords
        - Inverse Document Frequency (IDF): Rare terms weighted higher
        - Document Length Normalization: Short focused entries rank above long noisy ones
        
        Parameters: k1=1.5, b=0.75 (standard IR defaults)
        """
        if not keywords:
            return []
            
        import math
        
        # BM25 parameters
        k1 = 1.5   # Term frequency saturation
        b = 0.75   # Document length normalization

        # 1. Collect all entries from ALL scan directories
        all_entries = []
        # Memory directories (covers: CONTEXT, EXPERIENCE, DECISION, EMOTION, LEARNING, FACT, PROCEDURAL, REFLECTION, BELIEF, GOAL, HABIT, SYSTEM, A2A)
        memory_dirs = [
            "sessions", "experiences", "decisions", "emotions",
            "learnings", "facts", "procedures",
            "reflections", "beliefs",
            "goals", "habits",
            "system", "a2a"
        ]
        for d in memory_dirs:
            dir_path = os.path.join(self.base_path, "memory", d)
            if not os.path.exists(dir_path):
                continue
            for filename in os.listdir(dir_path):
                if not filename.endswith(".md"):
                    continue
                file_path = os.path.join(dir_path, filename)
                entries = self.load_all_from_file(file_path)
                all_entries.extend(entries)

        # 1b. Collect from Infrastructure/System directories
        sys_dirs = ["intuition", "metadata", "cache"]
        for d in sys_dirs:
            dir_path = os.path.join(self.base_path, "sys", d)
            if not os.path.exists(dir_path):
                continue
            for filename in os.listdir(dir_path):
                if filename.endswith(".md"):
                    file_path = os.path.join(dir_path, filename)
                    all_entries.extend(self.load_all_from_file(file_path))

        # 1c. Collect from Vault (Encrypted)
        vault_path = os.path.join(self.base_path, "vault")
        if os.path.exists(vault_path):
            for filename in os.listdir(vault_path):
                if filename.endswith(".md"):
                    file_path = os.path.join(vault_path, filename)
                    all_entries.extend(self.load_all_from_file(file_path))
        
        # Profile directories (USER_PROFILE, SENTIMENT, RELATIONSHIP, PERSONA)
        profile_dirs = ["users", "dynamics", "relationships", "identity"]
        for d in profile_dirs:
            dir_path = os.path.join(self.base_path, "profiles", d)
            if not os.path.exists(dir_path):
                continue
            for filename in os.listdir(dir_path):
                if not filename.endswith(".md"):
                    continue
                file_path = os.path.join(dir_path, filename)
                entries = self.load_all_from_file(file_path)
                all_entries.extend(entries)
        
        # Root-level memory files
        root_general = os.path.join(self.base_path, "memory", "general_memory.md")
        if os.path.exists(root_general):
            all_entries.extend(self.load_all_from_file(root_general))

        if not all_entries:
            return []

        # 2. Build document texts + compute avg document length
        doc_texts = []
        doc_lengths = []
        for entry in all_entries:
            text = f"{entry.key} {str(entry.value)}".lower()
            doc_texts.append(text)
            doc_lengths.append(len(text.split()))
        
        N = len(all_entries)  # Total document count
        avgdl = sum(doc_lengths) / N if N > 0 else 1  # Average document length
        
        # 3. Compute IDF for each keyword
        # IDF = log((N - df + 0.5) / (df + 0.5) + 1)
        keyword_idf = {}
        for kw in keywords:
            df = sum(1 for text in doc_texts if kw in text)  # Document frequency
            idf = math.log((N - df + 0.5) / (df + 0.5) + 1)
            keyword_idf[kw] = idf

        # 4. Score each document with BM25
        scored = []
        for i, entry in enumerate(all_entries):
            text = doc_texts[i]
            dl = doc_lengths[i]  # Current doc length
            
            score = 0.0
            for kw in keywords:
                # Term frequency in this document
                tf = text.count(kw)
                if tf == 0:
                    continue
                    
                # BM25 formula: IDF * (tf * (k1 + 1)) / (tf + k1 * (1 - b + b * dl / avgdl))
                idf = keyword_idf[kw]
                numerator = tf * (k1 + 1)
                denominator = tf + k1 * (1 - b + b * dl / avgdl)
                score += idf * (numerator / denominator)
            
            if score > 0:
                # Boost by importance (0-1 range, minor influence)
                score *= (1 + entry.importance * 0.3)
                scored.append((score, entry))
        
        # 5. Sort by BM25 score descending
        scored.sort(key=lambda x: x[0], reverse=True)
        
        # 6. Deduplicate by key and return top `limit`
        results = []
        seen_keys = set()
        for score, entry in scored:
            if entry.key not in seen_keys:
                seen_keys.add(entry.key)
                results.append(entry)
                if len(results) >= limit:
                    break
                    
        return results

