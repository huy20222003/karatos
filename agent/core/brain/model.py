import os
from typing import Optional
from langchain_ollama import ChatOllama
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, ToolMessage
from config.settings import settings
from utils.logger import get_logger

logger = get_logger()

from langchain_core.language_models.chat_models import BaseChatModel

class SharedModelProvider:
    _instance: Optional[BaseChatModel] = None

    @classmethod
    def get_model(cls) -> BaseChatModel:
        if cls._instance is None:
            provider = settings.llm_provider.lower()
            
            if provider == "ollama":
                from langchain_ollama import ChatOllama
                from .hardware import HardwareEngine
                
                # Dynamic Calibration (Specific to Local Ollama)
                threads = HardwareEngine.get_optimal_threads()
                ctx_size = HardwareEngine.get_optimal_context_size()
                
                logger.info(f"[MODEL_PROVIDER] Initializing Ollama: Model={settings.ollama_model_name}, Threads={threads}, Context={ctx_size}")
                
                cls._instance = ChatOllama(
                    base_url=settings.ollama_base_url,
                    model=settings.ollama_model_name,
                    temperature=settings.model_temperature,
                    num_ctx=ctx_size,
                    num_thread=threads,
                    num_predict=settings.model_max_tokens,
                    timeout=60.0,
                    additional_kwargs={
                        "num_parallel": settings.model_parallelism, 
                        "num_gpu": 1 if os.environ.get("USE_GPU", "true") == "true" else 0,
                        "keep_alive": "6h",
                        "stop": ["<|im_start|>", "<|im_end|>", "<|endoftext|>"]
                    },
                    client_kwargs={"headers": settings.ollama_headers}
                )
            
            elif provider == "openai":
                from langchain_openai import ChatOpenAI
                logger.info(f"[MODEL_PROVIDER] Initializing OpenAI Compatible: Model={settings.openai_model_name}")
                cls._instance = ChatOpenAI(
                    api_key=settings.openai_api_key,
                    base_url=settings.openai_api_base,
                    model=settings.openai_model_name,
                    temperature=settings.model_temperature,
                    max_tokens=settings.model_max_tokens,
                    timeout=60.0
                )
            
            elif provider == "anthropic":
                from langchain_anthropic import ChatAnthropic
                logger.info(f"[MODEL_PROVIDER] Initializing Anthropic: Model={settings.anthropic_model_name}")
                cls._instance = ChatAnthropic(
                    api_key=settings.anthropic_api_key,
                    model=settings.anthropic_model_name,
                    temperature=settings.model_temperature,
                    max_tokens=settings.model_max_tokens,
                    timeout=60.0
                )
            
            elif provider == "groq":
                from langchain_groq import ChatGroq
                logger.info(f"[MODEL_PROVIDER] Initializing Groq: Model={settings.groq_model_name}")
                cls._instance = ChatGroq(
                    api_key=settings.groq_api_key,
                    model=settings.groq_model_name,
                    temperature=settings.model_temperature,
                    max_tokens=settings.model_max_tokens,
                    timeout=60.0
                )
            else:
                raise ValueError(f"Unsupported LLM provider: {provider}")

            logger.info(f"[MODEL_PROVIDER] Provider '{provider}' initialized successfully.")
        return cls._instance

    _warmed: bool = False

    @classmethod
    async def warmup(cls):
        """Pre-warm the LLM model in background"""
        if cls._warmed:
            return
            
        model = cls.get_model()
        logger.info(f"[MODEL_PROVIDER] Pre-warming LLM '{settings.ollama_model_name}'...")
        try:
            import asyncio
            import time
            t_start = time.time()
            
            # Pulse with a greeting to force the model into VRAM
            await asyncio.wait_for(model.ainvoke("Hi"), timeout=120)
            
            cls._warmed = True
            logger.info(f"[MODEL_PROVIDER] LLM is warm and ready (Pulse took {time.time()-t_start:.2f}s).")
        except Exception as e:
            logger.warning(f"[MODEL_PROVIDER] LLM Warmup skipped or slow: {e}")

    @classmethod
    def set_model(cls, model: ChatOllama):
        cls._instance = model


class BrainModel:
    """
    Base class for all Brain components (Router, Planner, Generator, Critic).
    Centralizes identity, LLM access, and prompt formatting.
    """
    def __init__(self, mode: str):
        from core.identity import AgentIdentity
        self.model = SharedModelProvider.get_model()
        self.identity = AgentIdentity()
        self.mode = mode

    async def think(self, prompt: str, phase: str = None, mood: str = "OPTIMISTIC", energy: float = 1.0, timeout: float = None, tools: list = None):
        """Standard thinking implementation using standard Langchain Message objects."""
        import asyncio
        from config.settings import settings
        
        # 1. Update identity state
        self.identity.current_mood = mood
        self.identity.energy = energy
        
        # 2. Get system prompt for the specified phase (or use default mode)
        phase_to_use = phase or self.mode
        system_prompt = self.identity.get_system_prompt(phase_to_use)
        
        # 3. Message Formatting (No Hardcoded ChatML)
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=prompt)
        ]
        
        # 4. Bind Tools if provided
        llm_worker = self.model
        if tools:
            llm_worker = self.model.bind_tools(tools)

        # 5. Invoke LLM (with Retry Logic for Network Stability)
        max_retries = 2
        for attempt in range(max_retries + 1):
            try:
                actual_timeout = timeout or 60.0
                response = await asyncio.wait_for(llm_worker.ainvoke(messages), timeout=actual_timeout)
                
                # If tools were used, LLM returns tool_calls directly
                if tools and hasattr(response, 'tool_calls') and response.tool_calls:
                    return response.tool_calls
                
                from .utils import get_llm_content
                content = get_llm_content(response).strip()
                return content
            except Exception as e:
                # Catch Peer/Protocol errors for retry
                is_transient = any(msg in str(e).lower() for msg in ["remoteprotocolerror", "peer closed connection", "ngrok gateway error", "err_ngrok_3004"])
                if attempt < max_retries and is_transient:
                    wait_time = 1.0 * (attempt + 1)
                    logger.warning(f"[BRAIN_MODEL] Transient error in mode '{self.mode}' (Attempt {attempt+1}). Retrying in {wait_time}s...")
                    await asyncio.sleep(wait_time)
                    continue
                
                logger.error(f"[BRAIN_MODEL] Thinking failed in mode '{self.mode}': {repr(e)}")
                return "ERROR_TIMEOUT" if isinstance(e, asyncio.TimeoutError) else "ERROR_FAILED"


