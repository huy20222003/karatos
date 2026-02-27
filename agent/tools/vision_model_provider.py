"""
Vision Model Provider
Provides a provider-agnostic vision chat model and message builder.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

from config.settings import settings
from utils.logger import get_logger

logger = get_logger()


@dataclass
class VisionModelConfig:
    provider: str
    model_name: str


def _select_vision_model_name(provider: str) -> str:
    provider = provider.lower()
    if provider == "ollama":
        return settings.ollama_vision_model_name
    if provider == "openai":
        return getattr(settings, "openai_vision_model_name", None) or settings.openai_model_name
    if provider == "anthropic":
        return getattr(settings, "anthropic_vision_model_name", None) or settings.anthropic_model_name
    if provider == "groq":
        # Groq multimodal support is not guaranteed; fall back.
        return settings.ollama_vision_model_name
    return settings.ollama_vision_model_name


def get_vision_model() -> Tuple[object, VisionModelConfig]:
    """
    Return a LangChain chat model configured for vision, following settings.llm_provider
    when supported. If the selected provider does not support vision reliably, fall back
    to Ollama vision.
    """
    provider = (settings.llm_provider or "ollama").lower()
    model_name = _select_vision_model_name(provider)

    # Vision tasks prefer low temperature for extraction fidelity.
    temperature = 0.1

    if provider == "ollama":
        from langchain_ollama import ChatOllama
        model = ChatOllama(
            base_url=settings.ollama_base_url,
            model=model_name,
            temperature=temperature,
            headers=settings.ollama_headers,
        )
        return model, VisionModelConfig(provider="ollama", model_name=model_name)

    if provider == "openai":
        from langchain_openai import ChatOpenAI
        model = ChatOpenAI(
            api_key=settings.openai_api_key,
            base_url=settings.openai_api_base,
            model=model_name,
            temperature=temperature,
            max_tokens=settings.model_max_tokens,
            timeout=120.0,
        )
        return model, VisionModelConfig(provider="openai", model_name=model_name)

    if provider == "anthropic":
        from langchain_anthropic import ChatAnthropic
        model = ChatAnthropic(
            api_key=settings.anthropic_api_key,
            model=model_name,
            temperature=temperature,
            max_tokens=settings.model_max_tokens,
            timeout=120.0,
        )
        return model, VisionModelConfig(provider="anthropic", model_name=model_name)

    if provider == "groq":
        logger.warning("[VISION_PROVIDER] Provider 'groq' selected, falling back to Ollama vision.")
        from langchain_ollama import ChatOllama
        model = ChatOllama(
            base_url=settings.ollama_base_url,
            model=settings.ollama_vision_model_name,
            temperature=temperature,
            headers=settings.ollama_headers,
        )
        return model, VisionModelConfig(provider="ollama", model_name=settings.ollama_vision_model_name)

    logger.warning(f"[VISION_PROVIDER] Unsupported provider '{provider}', falling back to Ollama vision.")
    from langchain_ollama import ChatOllama
    model = ChatOllama(
        base_url=settings.ollama_base_url,
        model=settings.ollama_vision_model_name,
        temperature=temperature,
        headers=settings.ollama_headers,
    )
    return model, VisionModelConfig(provider="ollama", model_name=settings.ollama_vision_model_name)


def build_vision_human_message(*, provider: str, prompt: str, image_base64: str, mime_type: str):
    """
    Build a provider-compatible HumanMessage containing text + image.
    """
    from langchain_core.messages import HumanMessage

    provider = provider.lower()
    mime = mime_type or "image/jpeg"

    if provider == "anthropic":
        # Claude expects base64 image blocks with explicit media type.
        return HumanMessage(
            content=[
                {"type": "text", "text": prompt},
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": mime,
                        "data": image_base64,
                    },
                },
            ]
        )

    # OpenAI-compatible and Ollama-compatible formats both accept image_url blocks.
    return HumanMessage(
        content=[
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{image_base64}"}},
        ]
    )

