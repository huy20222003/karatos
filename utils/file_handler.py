import os
import asyncio
import uuid
from typing import Optional, Dict, Any
from pathlib import Path
from utils.logger import get_logger

logger = get_logger()

# Maximum allowed file size for Telegram downloads (bytes).
MAX_TELEGRAM_FILE_BYTES = 50 * 1024 * 1024  # 50 MB

def get_temp_path(file_type: str, filename: Optional[str] = None, chat_id: Optional[str] = None, ext: str = "") -> str:
    """
    Generates a standardized path within the project's tmp/ directory.
    file_type: 'voice', 'image', or 'file'
    """
    subfolder_map = {
        "voice": "voices",
        "image": "images",
        "file": "files"
    }
    prefix_map = {
        "voice": "voice_",
        "image": "image_",
        "file": "file_"
    }
    
    subfolder = subfolder_map.get(file_type, "others")
    prefix = prefix_map.get(file_type, "temp_")
    
    # Ensure tmp directory exists
    tmp_base = os.path.join("tmp", subfolder)
    os.makedirs(tmp_base, exist_ok=True)
    
    if not filename:
        # Generate a name if not provided
        suffix = ext if ext.startswith(".") else f".{ext}" if ext else ""
        if chat_id:
            filename = f"{prefix}{chat_id}{suffix}"
        else:
            filename = f"{prefix}{uuid.uuid4().hex}{suffix}"
    else:
        # Ensure prefix
        if not filename.startswith(prefix):
            filename = f"{prefix}{filename}"
            
    return os.path.join(tmp_base, filename)

def save_temp_data(data: bytes, file_type: str, filename: Optional[str] = None, chat_id: Optional[str] = None, ext: str = "") -> str:
    """
    Saves bytes to a standardized temp path and returns the absolute path.
    """
    path = get_temp_path(file_type, filename, chat_id, ext)
    with open(path, "wb") as f:
        f.write(data)
    return os.path.abspath(path)


async def prepare_telegram_file(
    channel,
    metadata: Dict[str, Any],
    default_name: str,
    default_mime: str,
) -> Optional[Dict[str, str]]:
    """
    Download a Telegram file into centered tmp/ directory, then return its metadata.
    """
    file_id = metadata.get("file_id")
    if not file_id:
        return None

    # Enforce size limit
    size_bytes = int(metadata.get("file_size") or 0)
    if size_bytes and size_bytes > MAX_TELEGRAM_FILE_BYTES:
        logger.warning(
            f"[FILE_HANDLER] Refusing to download file_id={file_id}: "
            f"size={size_bytes} exceeds limit={MAX_TELEGRAM_FILE_BYTES} bytes"
        )
        return None

    original_name = metadata.get("file_name", default_name)
    mime_type = metadata.get("mime_type", default_mime)

    # Choose file_type for standardized path
    file_type = "file"
    if "image" in mime_type.lower():
        file_type = "image"
    elif any(x in mime_type.lower() for x in ["audio", "voice", "ogg"]):
        file_type = "voice"

    # Generate standardized path via centralized handler
    local_path = get_temp_path(file_type, filename=original_name)

    logger.info(f"[FILE_HANDLER] Downloading file_id={file_id} to: {local_path}")

    # Delegate actual download to channel
    try:
        downloaded_path = await channel._download_file(file_id, local_path)
    except Exception as e:
        logger.error(f"[FILE_HANDLER] Download failed: {e}")
        return None

    if downloaded_path:
        resolved = Path(downloaded_path).resolve()
        logger.info(f"[FILE_HANDLER] File ready: {resolved}")
        return {
            "path": str(resolved),
            "name": original_name,
            "mime": mime_type,
        }
    return None

def cleanup_temp_file(file_path: Optional[str], source: str = "SYSTEM"):
    """
    Safely deletes a temporary file.
    """
    if not file_path:
        return
        
    if os.path.exists(file_path):
        try:
            # Normalize path for comparison
            abs_path = os.path.abspath(file_path)
            
            # Security: Ensure we only delete from allowed temp directories
            # Covers system temp and project-local tmp/
            is_temp_area = any(x in abs_path for x in ["temp", "tmp", "sandbox", "data\\storage"])
            is_temp_prefix = any(x in os.path.basename(abs_path) for x in ["file_", "image_", "voice_"])

            if is_temp_area and is_temp_prefix:
                os.remove(abs_path)
                logger.info(f"[{source}] 🧹 Cleaned up temp file: {abs_path}")
            else:
                logger.warning(f"[{source}] Skip cleanup for non-temp file or prefix: {abs_path}")
        except Exception as e:
            logger.error(f"[{source}] Cleanup failed: {e}")
