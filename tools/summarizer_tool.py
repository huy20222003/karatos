"""
Summarizer Tool
Summarizes long text content into concise insights using LLM.
"""
import asyncio
from typing import Any, Dict

from config.settings import settings
from utils.logger import get_logger

logger = get_logger()

TOOL_META = {
    "name": "summarizer_tool",
    "aliases": ["summarizer", "summarize", "tldr"],
    "class_name": "SummarizerTool",
    "description": "Summarizer: Condenses long text, articles, or documents into concise summaries with key insights.",
    "enabled": True,
    "author": "Karatos Core",
    "version": "1.0.0",
    "actions": [
        {
            "name": "summarize",
            "description": "Summarize a given text.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "The text to summarize."},
                    "max_length": {"type": "integer", "description": "Target summary length in words. Default: 200."},
                    "style": {"type": "string", "enum": ["brief", "detailed", "bullet_points"], "description": "Summary style."}
                },
                "required": ["text"]
            }
        }
    ]
}


class SummarizerTool:
    """LLM-powered text summarization."""

    @classmethod
    async def execute(cls, text: str = "", max_length: int = 200,
                      style: str = "brief", **kwargs) -> Dict[str, Any]:
        """Summarize long text into concise insights."""
        if not text:
            return {"status": "error", "message": "Missing 'text' parameter."}

        if len(text) < 100:
            return {
                "status": "success",
                "data": {"summary": text, "style": style, "note": "Text too short to summarize."}
            }

        style_instructions = {
            "brief": f"Summarize the following text in under {max_length} words. Be concise and capture the core message.",
            "detailed": f"Provide a detailed summary of the following text in about {max_length} words. Include key points, important details, and conclusions.",
            "bullet_points": f"Summarize the following text as a bullet-point list (max {max_length} words total). Each bullet should capture one key insight."
        }

        prompt = f"""{style_instructions.get(style, style_instructions['brief'])}

TEXT:
{text[:30000]}

SUMMARY:"""

        try:
            from core.brain.model import SharedModelProvider
            model = SharedModelProvider.get_model()
            
            response = await asyncio.wait_for(
                model.ainvoke(prompt),
                timeout=90.0
            )
            content = response.content if hasattr(response, "content") else str(response)

            logger.info(f"[SUMMARIZER] Summarized {len(text)} chars → {len(content)} chars ({style})")
            return {
                "status": "success",
                "data": {
                    "summary": content.strip(),
                    "style": style,
                    "original_length": len(text),
                    "summary_length": len(content)
                }
            }
        except asyncio.TimeoutError:
            return {"status": "error", "message": "Summarization timed out."}
        except Exception as e:
            logger.error(f"[SUMMARIZER] Failed: {e}")
            return {"status": "error", "message": f"Summarization failed: {str(e)}"}
