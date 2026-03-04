"""
Vision Reader Tool
Reads and understands image content using Ollama vision models.
Supports: OCR, general description, custom analysis prompts.
"""
import base64
import os
from typing import Any, Dict, Optional
from utils.logger import get_logger

logger = get_logger()

# Tool metadata for ToolRegistry auto-discovery
TOOL_META = {
    "name": "vision_reader",
    "aliases": ["vision", "read_image", "ocr", "describe_image"],
    "class_name": "VisionReader",
    "description": "Vision Reader: Analyzes images using AI vision models. Can extract text (OCR), describe visual content, and answer questions about images.",
    "enabled": True,
    "author": "Karatos Core",
    "version": "1.0.0",
    "actions": [
        {
            "name": "analyze_image",
            "description": "Analyze an image with a custom prompt or default description.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "image_path": {"type": "string", "description": "Absolute path to the image file."},
                    "image_base64": {"type": "string", "description": "Base64-encoded image data (alternative to path)."},
                    "prompt": {"type": "string", "description": "Custom analysis prompt. Default: general description + OCR."},
                    "mode": {"type": "string", "enum": ["describe", "extract_text", "analyze"], "description": "Analysis mode."}
                },
                "required": []
            }
        }
    ]
}


class VisionReader:
    """
    AI-powered image analysis using Ollama vision models.
    Default model: qwen2.5-vl:7b
    """

    # Model selection is delegated to VisionModelProvider.

    @staticmethod
    def _load_image_as_base64(image_path: str) -> Optional[str]:
        """Load an image file and convert to base64."""
        try:
            if not os.path.exists(image_path):
                logger.error(f"[VISION] Image file not found: {image_path}")
                return None
            with open(image_path, "rb") as f:
                return base64.b64encode(f.read()).decode("utf-8")
        except Exception as e:
            logger.error(f"[VISION] Failed to load image: {e}")
            return None

    @staticmethod
    def _get_mode_prompt(mode: str, custom_prompt: str = "") -> str:
        """Generate professional, high-fidelity prompts based on analysis mode."""
        prompts = {
            "describe": (
                "ACT AS AN EXPERT IMAGE ANALYST. Provide a professional, structured description of this image.\n"
                "STRICT CONSTRAINTS:\n"
                "- KEEP ALL EXTRACTED TEXT IN ITS ORIGINAL LANGUAGE. DO NOT TRANSLATE.\n"
                "- If text is in Vietnamese, English, or any other language, transcribe it character-for-character.\n\n"
                "STRUCTURE YOUR RESPONSE:\n"
                "1. **EXECUTIVE SUMMARY**: A high-level 1-sentence description of the image.\n"
                "2. **VISUAL COMPOSITION**: Describe main subjects, background, layout, and color palette.\n"
                "3. **TEXTUAL CONTENT (OCR)**: Extract ALL visible textExactly as it appears. Maintain line breaks.\n"
                "4. **TECHNICAL/UI ELEMENTS**: Identify buttons, icons, interface components, or metadata if present.\n"
                "5. **ATMOSPHERE & CONTEXT**: Describe the mood or the likely purpose of the image."
            ),
            "extract_text": (
                "ACT AS A HIGH-PRECISION OCR ENGINE. Your goal is to extract every piece of text from this image.\n"
                "CRITICAL RULES:\n"
                "- DO NOT TRANSLATE ANY TEXT. Keep the original language (Vietnamese, English, etc.).\n"
                "- MAINTAIN FORMATTING: Use markdown tables for tabular data. Use line breaks as seen in the image.\n"
                "- ACCURACY: If a character is unclear, use [?] but do not guess based on translation.\n"
                "- NO COMMENTARY: Return only the extracted text content unless no text is found (then state 'No text detected')."
            ),
            "analyze": custom_prompt or (
                "PERFORM COMPREHENSIVE MULTIMODAL ANALYSIS.\n"
                "OBJECTIVES:\n"
                "1. **OBSERVATION**: Detailed description of visual elements.\n"
                "2. **CONTENT EXTRACTION**: Precisely extract all text in its ORIGINAL LANGUAGE (No translation).\n"
                "3. **INTENT & PURPOSE**: What is the message or function of this image?\n"
                "4. **KEY INSIGHTS**: Identify anomalies, important data points, or unique features."
            )
        }
        return prompts.get(mode, prompts["analyze"])

    @classmethod
    async def analyze(cls, image_path: str = "", image_base64: str = "",
                      prompt: str = "", mode: str = "analyze",
                      **kwargs) -> Dict[str, Any]:
        """
        Analyze an image using the vision model.
        
        Args:
            image_path: Path to image file
            image_base64: Base64-encoded image (alternative)
            prompt: Custom analysis prompt
            mode: 'describe', 'extract_text', or 'analyze'
        """
        import asyncio

        # 1. Get image data
        img_b64 = image_base64
        if not img_b64 and image_path:
            img_b64 = cls._load_image_as_base64(image_path)
        
        if not img_b64:
            return {
                "status": "error",
                "message": "No image provided. Supply either 'image_path' or 'image_base64'."
            }

        # 2. Build prompt
        analysis_prompt = cls._get_mode_prompt(mode, prompt)
        logger.info(f"[VISION] Analyzing image (mode={mode}, prompt_len={len(analysis_prompt)})")

        # 3. Call vision model via provider-agnostic SharedModelProvider
        try:
            from core.brain.model import SharedModelProvider

            vision_model, cfg = SharedModelProvider.get_vision_model()

            mime_type = kwargs.get("mime_type") or "image/jpeg"
            message = SharedModelProvider.build_vision_human_message(
                provider=cfg.provider,
                prompt=analysis_prompt,
                image_base64=img_b64,
                mime_type=mime_type,
            )

            response = await asyncio.wait_for(
                vision_model.ainvoke([message]),
                timeout=120.0
            )

            content = response.content if hasattr(response, "content") else str(response)
            
            logger.info(f"[VISION] Analysis complete. Response length: {len(content)} chars")

            return {
                "status": "success",
                "data": {
                    "description": content.strip(),
                    "mode": mode,
                    "model": cfg.model_name,
                    "provider": cfg.provider,
                }
            }

        except asyncio.TimeoutError:
            logger.error("[VISION] Vision model timed out after 120s")
            return {
                "status": "error",
                "message": "Vision model timed out. The image may be too large or the model is busy."
            }
        except Exception as e:
            logger.error(f"[VISION] Analysis failed: {e}")
            return {
                "status": "error",
                "message": f"Vision analysis failed: {str(e)}"
            }

    @classmethod
    async def execute(cls, **params) -> Dict[str, Any]:
        """Universal entry point for tool registry."""
        return await cls.analyze(**params)
