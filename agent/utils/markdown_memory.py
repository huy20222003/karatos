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
        """Create storage hierarchy if missing"""
        # Private Bot Storage
        os.makedirs(self.base_path, exist_ok=True)
        os.makedirs(os.path.join(self.base_path, "memory", "sessions"), exist_ok=True)
        os.makedirs(os.path.join(self.base_path, "memory", "learnings"), exist_ok=True)
        os.makedirs(os.path.join(self.base_path, "memory", "decisions"), exist_ok=True)
        os.makedirs(os.path.join(self.base_path, "memory", "experiences"), exist_ok=True)
        os.makedirs(os.path.join(self.base_path, "memory", "reflections"), exist_ok=True)
        os.makedirs(os.path.join(self.base_path, "memory", "graph"), exist_ok=True)
        os.makedirs(os.path.join(self.base_path, "profiles", "users"), exist_ok=True)
        os.makedirs(os.path.join(self.base_path, "profiles", "identities"), exist_ok=True)
        os.makedirs(os.path.join(self.base_path, "profiles", "dynamics"), exist_ok=True)
        os.makedirs(os.path.join(self.base_path, "profiles", "identity"), exist_ok=True)
        os.makedirs(os.path.join(self.base_path, "sys", "cache"), exist_ok=True)
        os.makedirs(os.path.join(self.base_path, "sys", "intuition"), exist_ok=True)
        os.makedirs(os.path.join(self.base_path, "vault"), exist_ok=True)

    def _get_file_path(self, category: str, key: str) -> str:
        """Determines the correct file based on category and key."""
        category = category.upper()

        # PRIVATE CATEGORIES (Bot Specific)
        if category == "CONTEXT" or "chat:" in key:
            # chat_id from key "chat:chat_id:timestamp"
            if "chat:" in key:
                parts = key.split(":")
                if len(parts) > 1:
                    chat_id = parts[1]
                    return os.path.join(self.base_path, "memory", "sessions", f"{chat_id}.md")
            return os.path.join(self.base_path, "memory", "sessions", "general.md")
            
        if category == "USER_HISTORY" or "user_" in key:
            return os.path.join(self.base_path, "profiles", "users", "profiles.md")
            
        if category == "DECISION" or "dec:" in key:
            return os.path.join(self.base_path, "memory", "decisions", "history.md")
            
        if category == "LEARNING":
            return os.path.join(self.base_path, "memory", "learnings", "knowledge.md")

        if category == "EXPERIENCE":
            return os.path.join(self.base_path, "memory", "experiences", "history.md")

        if category == "REFLECTION":
            return os.path.join(self.base_path, "memory", "reflections", "lessons.md")

        if category == "SENTIMENT":
            return os.path.join(self.base_path, "profiles", "dynamics", "moods.md")
            
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
        categories = ["context", "user_history", "decision", "learning"]
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
        Phase 5: Fast Markdown Retrieval using regex/keyword matching.
        Scans all relevant text-based memory files for keyword overlaps.
        """
        if not keywords:
            return []
            
        import re
        matches = []
        
        # Directories to scan for semantic recall
        scan_dirs = ["learnings", "experiences", "reflections", "decisions"]
        
        for d in scan_dirs:
            dir_path = os.path.join(self.base_path, "memory", d)
            if not os.path.exists(dir_path):
                continue
                
            for filename in os.listdir(dir_path):
                if not filename.endswith(".md"):
                    continue
                file_path = os.path.join(dir_path, filename)
                entries = self.load_all_from_file(file_path)
                
                for entry in entries:
                    content_text = str(entry.value).lower()
                    key_text = entry.key.lower()
                    
                    # Count how many keywords match
                    match_count = sum(1 for k in keywords if k in content_text or k in key_text)
                    
                    if match_count > 0:
                        matches.append((match_count, entry))
        
        # Sort by match count (descending) and importance
        matches.sort(key=lambda x: (x[0], x[1].importance), reverse=True)
        
        # Deduplicate by key and return top `limit`
        results = []
        seen_keys = set()
        for count, entry in matches:
            if entry.key not in seen_keys:
                seen_keys.add(entry.key)
                results.append(entry)
                if len(results) >= limit:
                    break
                    
        return results
