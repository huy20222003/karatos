import os
import asyncio
import uuid
from typing import Optional, Dict, Any
from pathlib import Path
from utils.logger import get_logger

logger = get_logger()

# Maximum allowed file size for Telegram downloads (bytes).
MAX_TELEGRAM_FILE_BYTES = 50 * 1024 * 1024  # 50 MB


async def prepare_telegram_file(
    channel,
    metadata: Dict[str, Any],
    default_name: str,
    default_mime: str,
) -> Optional[Dict[str, str]]:
    """
    Download a Telegram file into an isolated sandbox directory using
    a randomized filename, then return its metadata (path, name, mime).
    """
    file_id = metadata.get("file_id")
    if not file_id:
        return None

    # Enforce size limit (if Telegram provided file_size metadata).
    size_bytes = int(metadata.get("file_size") or 0)
    if size_bytes and size_bytes > MAX_TELEGRAM_FILE_BYTES:
        logger.warning(
            f"[FILE_HANDLER] Refusing to download file_id={file_id}: "
            f"size={size_bytes} exceeds limit={MAX_TELEGRAM_FILE_BYTES} bytes"
        )
        return None

    original_name = metadata.get("file_name", default_name)
    mime_type = metadata.get("mime_type", default_mime)

    # Create sandbox directory under project root: data/tmp_telegram
    try:
        base_dir = Path(__file__).parent.parent  # agent/
        sandbox_dir = (base_dir / "data" / "tmp_telegram").resolve()
        sandbox_dir.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        logger.error(f"[FILE_HANDLER] Failed to initialize sandbox directory: {e}")
        return None

    # Generate a randomized, non-guessable filename, preserving extension only.
    ext = Path(original_name).suffix or ""
    safe_name = f"niva_tmp_{uuid.uuid4().hex}{ext}"
    local_path = sandbox_dir / safe_name

    logger.info(f"[FILE_HANDLER] Downloading file_id={file_id} to sandbox: {local_path}")

    # Delegate actual download to channel; ensure it writes to our sandbox path.
    try:
        # Channel implementation should respect the explicit target path.
        downloaded_path = await channel._download_file(file_id, str(local_path))
    except TypeError:
        # Backward compatibility: some implementations may accept only a name.
        downloaded_path = await channel._download_file(file_id, safe_name)

    if downloaded_path:
        resolved = Path(downloaded_path).resolve()
        # Double-check that the file still lives inside our sandbox.
        try:
            resolved.relative_to(sandbox_dir)
        except ValueError:
            logger.warning(f"[FILE_HANDLER] Downloaded path outside sandbox, ignoring: {resolved}")
            return None

        logger.info(f"[FILE_HANDLER] File ready in sandbox: {resolved}")
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
            # Basic safety check to ensure we only delete temp/sandbox files
            if "niva_sandbox_" in str(file_path) or "niva_tmp_" in str(file_path):
                os.remove(file_path)
                logger.info(f"[{source}] 🧹 Cleaned up temp file: {file_path}")
            else:
                logger.warning(f"[{source}] Skip cleanup for non-temp file: {file_path}")
        except Exception as e:
            logger.error(f"[{source}] Cleanup failed: {e}")
