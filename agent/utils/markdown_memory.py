import os
import yaml
import json
from datetime import datetime
from typing import Any, List, Optional, Dict
from dataclasses import dataclass, asdict

from utils.logger import get_logger
from utils.crypto import decrypt_file, write_encrypted

logger = get_logger()

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
        markdown_block = f"""
---
{yaml.dump(frontmatter, sort_keys=False).strip()}
---
{content_body}

"""
        try:
            write_encrypted(file_path, markdown_block, mode="a")
            logger.debug(f"[MD_MEMORY] Appended (encrypted) to {file_path}")
        except Exception as e:
            logger.error(f"[MD_MEMORY] Write failed: {e}")

    def load_all_from_file(self, file_path: str) -> List[MarkdownMemoryEntry]:
        """Parses a markdown file and returns all entries"""
        if not os.path.exists(file_path):
            return []
            
        entries = []
        try:
            content = decrypt_file(file_path)
            if not content:
                return []
                
            # Regex or split based on --- delimiters
            parts = content.split("---")
            # Parts should be: ["", yaml, body, yaml, body, ...] or similar
            # If split correctly, even indices (starting 1) are YAML, odd are Body
            
            i = 1
            while i < len(parts):
                try:
                    meta_raw = parts[i].strip()
                    body_raw = parts[i+1].strip() if i+1 < len(parts) else ""
                    
                    meta = yaml.safe_load(meta_raw)
                    if not meta or "key" not in meta:
                        i += 2
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
                i += 2
                
            return entries
        except Exception as e:
            logger.error(f"[MD_MEMORY] Load failed for {file_path}: {e}")
            return []

    def find_by_key(self, key: str) -> Optional[MarkdownMemoryEntry]:
        """Scans relevant files for a specific key"""
        # We don't know the exact file for just any key, but we can guess by prefix
        # or search all (for now, let's keep it simple as it's a fallback)
        categories = ["context", "user_history", "decision", "learning", "a2a"]
        for cat in categories:
            file_path = self._get_file_path(cat, key)
            entries = self.load_all_from_file(file_path)
            for entry in entries:
                if entry.key == key:
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
