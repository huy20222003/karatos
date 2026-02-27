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
            
            provider = (settings.llm_provider or "").lower().strip().replace("-", "_")
            
            try:
                if provider == "ollama":
                    from langchain_ollama import OllamaEmbeddings
                    cls._instance.model_name = settings.ollama_embedding_model_name
                    cls._embeddings = OllamaEmbeddings(
                        base_url=settings.ollama_base_url,
                        model=cls._instance.model_name,
                        client_kwargs={"headers": settings.ollama_headers}
                    )
                elif provider == "openai":
                    from langchain_openai import OpenAIEmbeddings
                    cls._instance.model_name = settings.openai_model_name
                    cls._embeddings = OpenAIEmbeddings(
                        api_key=settings.openai_api_key,
                        base_url=settings.openai_api_base,
                        model=cls._instance.model_name
                    )
                elif provider == "deepseek":
                    from langchain_openai import OpenAIEmbeddings
                    cls._instance.model_name = settings.deepseek_model_name
                    cls._embeddings = OpenAIEmbeddings(
                        api_key=settings.deepseek_api_key,
                        base_url="https://api.deepseek.com/v1",
                        model=cls._instance.model_name
                    )
                elif provider in ["anthropic", "claude_web"]:
                    # These use the user's custom proxy to get embeddings, just like Chat.
                    from langchain_core.embeddings import Embeddings
                    import httpx
                    
                    class ProxyEmbeddings(Embeddings):
                        def __init__(self, endpoint: str, model: str):
                            self.endpoint = endpoint
                            self.model = model
                            
                        def embed_documents(self, texts: list[str]) -> list[list[float]]:
                            results = []
                            for text in texts:
                                results.append(self.embed_query(text))
                            return results
                            
                        def embed_query(self, text: str) -> list[float]:
                            try:
                                payload = {"input": text, "model": self.model}
                                embedding_url = self.endpoint.replace("/completion", "/embeddings").replace("/direct", "/embeddings")
                                with httpx.Client(timeout=60.0) as client:
                                    resp = client.post(embedding_url, json=payload)
                                    if resp.status_code == 200:
                                        data = resp.json()
                                        return data.get("embedding") or data.get("data", [{}])[0].get("embedding", [])
                                    else:
                                        logger.error(f"[EMBEDDING] Proxy error {resp.status_code}: {resp.text}")
                                        return []
                            except Exception as e:
                                logger.error(f"[EMBEDDING] Proxy request failed: {e}")
                                return []

                        async def aembed_documents(self, texts: list[str]) -> list[list[float]]:
                            return self.embed_documents(texts)
                            
                        async def aembed_query(self, text: str) -> list[float]:
                            return self.embed_query(text)

                    cls._instance.model_name = settings.anthropic_model_name if provider == "anthropic" else settings.claude_web_model_name
                    cls._embeddings = ProxyEmbeddings(settings.claude_web_endpoint, cls._instance.model_name)
                    logger.info(f"[EMBEDDING] Proxy initialized for '{provider}' using model '{cls._instance.model_name}'")
                else:
                    logger.error(f"[EMBEDDING] Unsupported provider: {provider}")
                    cls._embeddings = None
                
                if cls._embeddings and not isinstance(cls._embeddings, (ProxyEmbeddings if 'ProxyEmbeddings' in locals() else type(None))):
                    logger.info(f"[EMBEDDING] Initialized using model '{cls._instance.model_name}'")
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
        """Pre-warm the embedding model (Ollama only)"""
        provider = (settings.llm_provider or "").lower().strip().replace("-", "_")
        if not self.embeddings or provider != "ollama":
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
