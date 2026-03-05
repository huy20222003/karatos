from datetime import datetime
from typing import List, Optional
import os
import numpy as np

# Suppress HuggingFace Hub warnings on startup
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

from sentence_transformers import SentenceTransformer
from config.settings import settings
from utils.logger import get_logger

logger = get_logger()

class EmbeddingEngine:
    """
    Pure library-based Embedding Engine using sentence-transformers.
    Model weights are cached on disk (~/.cache/huggingface/) and loaded from there.
    """
    
    _instance = None
    _model = None
    
    def __init__(self):
        # Prevent direct instantiation
        if EmbeddingEngine._instance is not None:
            raise RuntimeError("Use get_embedding_engine() instead of EmbeddingEngine()")

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = EmbeddingEngine.__new__(cls)
            cls._instance.model_name = getattr(settings, "memory_embedding_model", "sentence-transformers/all-MiniLM-L6-v2")
            
            try:
                import time
                t0 = time.time()
                # Try loading from local cache first (no network call, faster)
                try:
                    cls._model = SentenceTransformer(
                        cls._instance.model_name,
                        local_files_only=True,
                        show_progress_bar=False
                    )
                except Exception:
                    # Not cached yet — download once
                    logger.info(f"[EMBEDDING] First-time download: {cls._instance.model_name}...")
                    cls._model = SentenceTransformer(cls._instance.model_name)
                elapsed = time.time() - t0
                logger.info(f"[EMBEDDING] Model ready ({elapsed:.1f}s) — {cls._instance.model_name}")
            except Exception as e:
                logger.error(f"[EMBEDDING] Failed to load model: {e}")
                cls._model = None
        return cls._instance

    async def get_embedding(self, text: str) -> Optional[List[float]]:
        """Generate an embedding for a single string. (Async for compatibility)"""
        if not self._model or not text:
            return None
        try:
            # Clean text: remove newlines and extra spaces
            clean_text = " ".join(text.split())
            # Encoding is fast enough synchronously, but we wrap in async for API consistency
            import asyncio
            vector = await asyncio.to_thread(self._model.encode, [clean_text])
            return vector[0].tolist()
        except Exception as e:
            logger.error(f"[EMBEDDING] Generation failed: {e}")
            return None

    async def get_embeddings(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for a list of strings (batched)."""
        if not self._model or not texts:
            return []
        try:
            clean_texts = [" ".join(t.split()) for t in texts]
            import asyncio
            vectors = await asyncio.to_thread(self._model.encode, clean_texts)
            return vectors.tolist()
        except Exception as e:
            logger.error(f"[EMBEDDING] Batch generation failed: {e}")
            return []

    async def warmup(self):
        """Pre-warm the embedding model into VRAM/RAM."""
        if not self._model:
            return
        try:
            self._model.encode(["warmup"])
        except Exception:
            pass

# Singleton accessor
def get_embedding_engine() -> EmbeddingEngine:
    return EmbeddingEngine.get_instance()
