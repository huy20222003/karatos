import os
import json
import numpy as np
import faiss
from typing import List, Optional, Any, Dict, Set
from dataclasses import dataclass, asdict
from utils.logger import get_logger
from utils.crypto import encrypt_text, decrypt_text
from utils.helpers import safe_json_dumps

logger = get_logger()

@dataclass
class FileVectorEntry:
    key: str
    category: str
    content: Any  # Should be encrypted in file
    importance: float
    vector: np.ndarray
    created_at: str
    expires_at: Optional[str] = None
    score: float = 0.0

    def to_dict(self) -> dict:
        d = asdict(self)
        d['vector'] = self.vector.tolist()
        return d

    @classmethod
    def from_dict(cls, data: dict) -> 'FileVectorEntry':
        data['vector'] = np.array(data['vector'])
        return cls(**data)

class FileVectorEngine:
    """
    Enhanced Pure File-based Vector Storage Engine with FAISS HNSW acceleration.
    JSON files remain the source of truth. FAISS provides sub-millisecond search.
    """
    
    CATEGORY_MAP = {
        "CONTEXT": "memory/sessions",
        "EXPERIENCE": "memory/experiences",
        "DECISION": "memory/decisions",
        "EMOTION": "memory/emotions",
        "LEARNING": "memory/learnings",
        "FACT": "memory/facts",
        "PROCEDURAL": "memory/procedures",
        "PERSONA": "profiles/identity",
        "REFLECTION": "memory/reflections",
        "BELIEF": "memory/beliefs",
        "USER_PROFILE": "profiles/users",
        "USER_HISTORY": "profiles/users",
        "RELATIONSHIP": "profiles/relationships",
        "SENTIMENT": "memory/emotions",
        "GOAL": "memory/goals",
        "HABIT": "memory/habits",
        "SYSTEM": "memory/system",
        "METADATA": "sys/metadata",
        "A2A": "memory/a2a",
        "INTUITION": "sys/intuition",
        "PROMISE": "memory/promises",
        "VAULT": "vault",
        "CACHE": "sys/cache"
    }

    def __init__(self, base_path: str = "data/storage"):
        self.base_path = base_path
        self.index_path = os.path.join(self.base_path, "vector_index.faiss")
        self.mapping_path = os.path.join(self.base_path, "index_mapping.json")
        
        # In-memory FAISS structures
        self.index: Optional[faiss.Index] = None
        self.id_to_key: Dict[int, Dict[str, str]] = {} # id -> {"key": k, "category": c}
        self.key_to_id: Dict[str, int] = {} # "category:key" -> id
        self.dimension = 384 # Default for all-MiniLM-L6-v2
        
        # Initialize directory structure
        for sub_path in self.CATEGORY_MAP.values():
            full_path = os.path.join(self.base_path, sub_path)
            os.makedirs(full_path, exist_ok=True)
            
        self._init_faiss()
        logger.info(f"[FILE_VECTOR] FAISS HNSW Engine initialized. Dimension: {self.dimension}")

    def _init_faiss(self):
        """Load index from disk or rebuild from JSON files."""
        if os.path.exists(self.index_path) and os.path.exists(self.mapping_path):
            try:
                self.index = faiss.read_index(self.index_path)
                with open(self.mapping_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    # JSON keys are strings, convert back to int
                    self.id_to_key = {int(k): v for k, v in data.get("id_to_key", {}).items()}
                    self.key_to_id = data.get("key_to_id", {})
                logger.info(f"[FAISS] Loaded index with {self.index.ntotal} vectors from disk.")
                return
            except Exception as e:
                logger.warning(f"[FAISS] Failed to load index: {e}. Rebuilding...")

        self._rebuild_index()

    def _rebuild_index(self):
        """Scan all JSON files and build a fresh HNSW index."""
        logger.info("[FAISS] Rebuilding index from JSON files...")
        
        # Create HNSW index
        # M = 32 (links per node), efConstruction = 40
        self.index = faiss.IndexHNSWFlat(self.dimension, 32)
        self.index.hnsw.efConstruction = 40
        
        self.id_to_key = {}
        self.key_to_id = {}
        
        vectors = []
        mappings = []
        
        all_folders = set(self.CATEGORY_MAP.values())
        for folder in all_folders:
            full_folder = os.path.join(self.base_path, folder)
            if not os.path.exists(full_folder): continue
            
            for filename in os.listdir(full_folder):
                if not filename.endswith(".json") or filename == "index_mapping.json":
                    continue
                
                try:
                    with open(os.path.join(full_folder, filename), "r", encoding="utf-8") as f:
                        data = json.load(f)
                        vec = np.array(data['vector'], dtype='float32')
                        # Sanity check dimension
                        if vec.shape[0] != self.dimension:
                            continue
                        
                        vectors.append(vec)
                        mappings.append({
                            "key": data['key'],
                            "category": data['category']
                        })
                except:
                    continue
        
        if vectors:
            vectors_np = np.vstack(vectors).astype('float32')
            # FAISS HNSW requires training if using some IVFs, but FlatHNSW doesn't.
            # We add them and get IDs based on order.
            self.index.add(vectors_np)
            
            for i, mapping in enumerate(mappings):
                self.id_to_key[i] = mapping
                self.key_to_id[f"{mapping['category']}:{mapping['key']}"] = i
                
            self._save_index()
            logger.info(f"[FAISS] Rebuild complete. Indexed {len(vectors)} memories.")
        else:
            logger.info("[FAISS] No memories found to index.")

    def _save_index(self):
        """Persist index and mapping to disk."""
        try:
            faiss.write_index(self.index, self.index_path)
            with open(self.mapping_path, "w", encoding="utf-8") as f:
                json.dump({
                    "id_to_key": self.id_to_key,
                    "key_to_id": self.key_to_id
                }, f, ensure_ascii=False, indent=2)
            logger.debug("[FAISS] Index persisted to disk.")
        except Exception as e:
            logger.error(f"[FAISS] Failed to save index: {e}")

    def _get_file_path(self, key: str, category: str) -> str:
        """Map key and category to a safe file path."""
        folder = self.CATEGORY_MAP.get(category, "memory/system")
        safe_key = "".join([c if c.isalnum() or c in "-_" else "_" for c in key])
        if len(safe_key) > 100:
            safe_key = safe_key[:100] + "_" + str(hash(key))
        return os.path.join(self.base_path, folder, f"{safe_key}.json")

    def upsert(self, entry: FileVectorEntry):
        """Save vector entry to file and update FAISS index."""
        file_path = self._get_file_path(entry.key, entry.category)
        
        # 1. Update JSON Source of Truth
        data = entry.to_dict()
        if isinstance(entry.content, (dict, list)):
            plaintext = safe_json_dumps(entry.content)
        else:
            plaintext = str(entry.content)
            
        data['content'] = f"ENC::{encrypt_text(plaintext)}"
        
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"[FILE_VECTOR] Failed to save {file_path}: {e}")
            return

        # 2. Update FAISS Index
        vec = entry.vector.astype('float32').reshape(1, -1)
        full_key = f"{entry.category}:{entry.key}"
        
        if full_key in self.key_to_id:
            # FAISS HNSW Flat doesn't easily support updating a specific ID.
            # For local scale, we'll just rebuild the index if we want high accuracy,
            # or for now, we'll just append and the mapping will point to the NEW id.
            # Actually, let's just mark for rebuild or rebuild immediately if small.
            # Optimization: If index is small (< 1000), just rebuild.
            if self.index.ntotal < 1000:
                self._rebuild_index()
            else:
                # Just append, search will find the latest one (if we handle overlaps)
                # But to keep mapping clean:
                new_id = self.index.ntotal
                self.index.add(vec)
                self.id_to_key[new_id] = {"key": entry.key, "category": entry.category}
                self.key_to_id[full_key] = new_id
                self._save_index()
        else:
            new_id = self.index.ntotal
            self.index.add(vec)
            self.id_to_key[new_id] = {"key": entry.key, "category": entry.category}
            self.key_to_id[full_key] = new_id
            self._save_index()

    def get(self, key: str, category: str) -> Optional[FileVectorEntry]:
        """Load and decrypt a specific entry."""
        file_path = self._get_file_path(key, category)
        if not os.path.exists(file_path):
            return None
            
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            # Decrypt content
            content_val = data['content']
            if isinstance(content_val, str) and content_val.startswith("ENC::"):
                decrypted = decrypt_text(content_val[5:])
                try:
                    data['content'] = json.loads(decrypted)
                except:
                    data['content'] = decrypted
            
            return FileVectorEntry.from_dict(data)
        except Exception as e:
            logger.error(f"[FILE_VECTOR] Failed to load {file_path}: {e}")
            return None

    def search(self, query_vector: np.ndarray, limit: int = 10, category: Optional[str] = None) -> List[FileVectorEntry]:
        """
        Global or Category-based Semantic Search using FAISS HNSW.
        Returns Top-K results with decrypted content.
        """
        if self.index is None or self.index.ntotal == 0:
            return []
            
        # FAISS search
        q_vec = query_vector.astype('float32').reshape(1, -1)
        # Search for more than limit to allow filtering by category if needed
        search_limit = limit * 5 if category else limit
        distances, indices = self.index.search(q_vec, min(search_limit, self.index.ntotal))
        
        results: List[FileVectorEntry] = []
        seen_keys = set() # Avoid duplicates if we appended updates
        
        for dist, idx in zip(distances[0], indices[0]):
            if idx == -1 or idx not in self.id_to_key: continue
            
            mapping = self.id_to_key[idx]
            # Filter by category if requested
            if category and mapping['category'] != category:
                continue
            
            # Key deduplication (latest first)
            full_key = f"{mapping['category']}:{mapping['key']}"
            if full_key in seen_keys: continue
            seen_keys.add(full_key)
            
            # Load full entry (Source of Truth)
            entry = self.get(mapping['key'], mapping['category'])
            if entry:
                # FAISS uses L2 distance for IndexHNSWFlat by default
                # Conversion to similarity score (higher is better)
                # For Normalized vectors, L2 = 2 - 2*CosineSim
                # So CosineSim = 1 - (L2 / 2)
                entry.score = float(1.0 / (1.0 + dist)) # Simple similarity proxy
                results.append(entry)
                
            if len(results) >= limit: break
            
        return results

    def delete(self, key: str, category: str) -> bool:
        """Delete entry file and rebuild index."""
        file_path = self._get_file_path(key, category)
        if os.path.exists(file_path):
            os.remove(file_path)
            # Rebuild index to remove from ANN search
            self._rebuild_index()
            return True
        return False

    def list_by_category(self, category: str, limit: int = 50) -> List[FileVectorEntry]:
        """List all entries in a category using the filesystem (not index)."""
        results = []
        folder = self.CATEGORY_MAP.get(category)
        if not folder: return []
            
        full_folder = os.path.join(self.base_path, folder)
        if not os.path.exists(full_folder): return []
            
        files = os.listdir(full_folder)
        # Sort by mtime descending for "recent" first
        files.sort(key=lambda x: os.path.getmtime(os.path.join(full_folder, x)), reverse=True)
        
        for filename in files:
            if not filename.endswith(".json"): continue
            
            try:
                with open(os.path.join(full_folder, filename), "r", encoding="utf-8") as f:
                    data = json.load(f)
                entry = self.get(data['key'], data['category'])
                if entry:
                    results.append(entry)
            except:
                continue
                
            if len(results) >= limit: break
        return results

    def get_count(self) -> int:
        return self.index.ntotal if self.index else 0

    def clear(self):
        """Wipe all memory files and index."""
        for folder in set(self.CATEGORY_MAP.values()):
            full_folder = os.path.join(self.base_path, folder)
            if os.path.exists(full_folder):
                for f in os.listdir(full_folder):
                    os.remove(os.path.join(full_folder, f))
        
        if os.path.exists(self.index_path): os.remove(self.index_path)
        if os.path.exists(self.mapping_path): os.remove(self.mapping_path)
        self._rebuild_index()
