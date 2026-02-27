"""
Audio Processor Tool
Transcribes audio/voice messages to text using Whisper.
"""
import os
import asyncio
from typing import Any, Dict

from utils.logger import get_logger
from config.settings import settings

logger = get_logger()

TOOL_META = {
    "name": "audio_processor",
    "aliases": ["audio", "transcribe", "speech_to_text", "voice"],
    "class_name": "AudioProcessor",
    "description": "Audio Processor: Transcribes voice messages and audio files to text using Whisper speech recognition.",
    "actions": [
        {
            "name": "transcribe",
            "description": "Convert audio/voice to text.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "file_path": {"type": "string", "description": "Path to the audio file (mp3, wav, ogg, m4a). Leave blank if processing a voice message."},
                    "language": {"type": "string", "description": "Language hint (e.g., 'vi', 'en'). Default: auto-detect."}
                },
                "required": ["file_path"]
            }
        }
    ]
}


class AudioProcessor:
    """Speech-to-text using faster-whisper with model caching."""

    SUPPORTED_FORMATS = {".mp3", ".wav", ".ogg", ".m4a", ".flac", ".webm", ".oga", ".opus", ".amr"}
    _model_cache = {}

    @classmethod
    def _get_model(cls, model_size: str = None):
        """Get or initialize a cached Whisper model."""
        if model_size is None:
            model_size = settings.whisper_model_size or "small"
            
        if model_size not in cls._model_cache:
            from faster_whisper import WhisperModel
            logger.info(f"[AUDIO] Initializing Whisper model: {model_size}")
            # Use CPU for general compatibility, int8 for speed
            cls._model_cache[model_size] = WhisperModel(model_size, device="cpu", compute_type="int8")
        return cls._model_cache[model_size]

    @classmethod
    async def execute(cls, file_path: str = "", language: str = None, **kwargs) -> Dict[str, Any]:
        """Transcribe an audio file to text."""
        if not file_path:
            # Check context if file_path is missing in direct params
            file_path = kwargs.get("context", {}).get("file_path")
            
        if not file_path:
            return {"status": "error", "message": "Missing 'file_path' parameter."}

        if not os.path.exists(file_path):
            return {"status": "error", "message": f"Audio file not found: {file_path}"}

        ext = os.path.splitext(file_path)[1].lower()
        if ext not in cls.SUPPORTED_FORMATS:
            return {
                "status": "error",
                "message": f"Unsupported audio format: {ext}. Supported: {', '.join(cls.SUPPORTED_FORMATS)}"
            }

        logger.info(f"[AUDIO] Transcribing: {file_path} (lang={language or 'auto'})")

        try:
            # Use cached faster-whisper model
            loop = asyncio.get_event_loop()
            
            def _transcribe():
                model = cls._get_model() # Uses settings.whisper_model_size
                # Whisper expects None for auto-detection, not 'auto'
                lang_code = language if language != "auto" else None
                segments, info = model.transcribe(
                    file_path,
                    language=lang_code,
                    beam_size=5,
                    vad_filter=True
                )
                text_parts = []
                for segment in segments:
                    text_parts.append(segment.text.strip())
                return " ".join(text_parts), info

            text, info = await loop.run_in_executor(None, _transcribe)

            if not text.strip():
                return {
                    "status": "success",
                    "data": {
                        "text": "",
                        "note": "No speech detected in the audio.",
                        "language_detected": getattr(info, "language", "unknown")
                    }
                }

            logger.info(f"[AUDIO] Transcription complete: {len(text)} chars, lang={getattr(info, 'language', 'unknown')}")
            return {
                "status": "success",
                "data": {
                    "text": text.strip(),
                    "language_detected": getattr(info, "language", "unknown"),
                    "language_probability": round(getattr(info, "language_probability", 0), 3),
                    "duration_seconds": round(getattr(info, "duration", 0), 1)
                }
            }
        except ImportError:
            logger.warning("[AUDIO] faster-whisper not installed. Falling back to shell whisper.")
            return {"status": "error", "message": "Audio processing library (faster-whisper) is not installed. Please install it with: pip install faster-whisper"}
        except Exception as e:
            logger.error(f"[AUDIO] Transcription failed: {e}")
            return {"status": "error", "message": f"Audio transcription failed: {str(e)}"}
