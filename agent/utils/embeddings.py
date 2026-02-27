"""
Embedding Utility
Provides text embedding capabilities using Ollama.
Essential for Vector Memory and Semantic Search.
"""
from datetime import datetime
from typing import List, Optional
import numpy as np

from langchain_ollama import OllamaEmbeddings
from config.settings import settings
from utils.logger import get_logger

logger = get_logger()

class EmbeddingEngine:
    """
    Wrapper for generating text embeddings via Ollama.
    Uses 'nomic-embed-text' as the default model.
    """
    
    _instance = None
    _embeddings = None
    
    def __init__(self):
        # Prevent direct instantiation
        if EmbeddingEngine._instance is not None:
            raise RuntimeError("Use get_embedding_engine() instead of EmbeddingEngine()")

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = EmbeddingEngine.__new__(cls)
            cls._instance.model_name = settings.ollama_embedding_model_name
            try:
                pass
                cls._embeddings = OllamaEmbeddings(
                    base_url=settings.ollama_base_url,
                    model=cls._instance.model_name,
                    client_kwargs={"headers": settings.ollama_headers}
                )
                pass
            except Exception as e:
                logger.error(f"[EMBEDDING] Failed to initialize: {e}")
                cls._embeddings = None
        return cls._instance

    @property
    def embeddings(self):
        return self._embeddings

    async def get_embedding(self, text: str) -> Optional[List[float]]:
        """Generate an embedding for a single string with retry logic and timeout"""
        import asyncio
        import time
        if not self.embeddings or not text:
            return None
            
        max_retries = 3
        base_timeout = 80.0 # Increased from 60s
        
        for attempt in range(max_retries):
            try:
                # Clean text: remove newlines and extra spaces
                clean_text = " ".join(text.split())
                t_start = time.time()
                
                # Use exponential backoff for timeout if it's a retry
                current_timeout = base_timeout + (attempt * 20)
                
                vector = await asyncio.wait_for(
                    self.embeddings.aembed_query(clean_text), 
                    timeout=current_timeout
                )
                
                return vector
                
            except asyncio.TimeoutError:
                if attempt < max_retries - 1:
                    await asyncio.sleep(1.0 * (attempt + 1)) # Small delay before retry
                else:
                    logger.error(f"[EMBEDDING] All {max_retries} attempts failed due to timeout.")
            except Exception as e:
                logger.error(f"[EMBEDDING] Error on attempt {attempt+1}: {e}")
                if attempt == max_retries - 1:
                    return None
                await asyncio.sleep(0.5)
                
        return None

    async def get_embeddings(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for a list of strings (batched) with retry logic and timeout"""
        import asyncio
        import time
        if not self.embeddings or not texts:
            return []
            
        max_retries = 3
        base_timeout = 150.0 # Increased from 120s
        
        for attempt in range(max_retries):
            try:
                clean_texts = [" ".join(t.split()) for t in texts]
                t_start = time.time()
                
                # Exponential backoff for batch timeout
                current_timeout = base_timeout + (attempt * 30)
                
                vectors = await asyncio.wait_for(
                    self.embeddings.aembed_documents(clean_texts), 
                    timeout=current_timeout
                )
                
                return vectors
                
            except asyncio.TimeoutError:
                if attempt < max_retries - 1:
                    await asyncio.sleep(2.0 * (attempt + 1))
                else:
                    logger.error(f"[EMBEDDING] All {max_retries} batch attempts failed.")
            except Exception as e:
                logger.error(f"[EMBEDDING] Batch error on attempt {attempt+1}: {e}")
                if attempt == max_retries - 1:
                    return []
                await asyncio.sleep(1.0)
                
        return []

    async def warmup(self):
        """Pre-warm the embedding model by sending a small request"""
        if not self.embeddings:
            return
        try:
            # Short pulse to trigger Ollama load
            await self.get_embedding("warmup")
        except Exception as e:
            pass

# Singleton instance
_engine = None

def get_embedding_engine() -> EmbeddingEngine:
    return EmbeddingEngine.get_instance()
