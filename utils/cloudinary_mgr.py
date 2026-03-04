"""
Cloudinary Upload Manager
Handles uploading images and audio to Cloudinary in the background.
Returns a public URL to store in memory instead of heavy Base64 strings.
"""
import asyncio
import base64
from typing import Optional
from utils.logger import get_logger

logger = get_logger()


def _configure():
    """Lazy-configure Cloudinary SDK from settings (called once)."""
    import cloudinary
    from config.settings import settings

    cloud = settings.cloudinary_cloud_name
    key = settings.cloudinary_api_key
    secret = settings.cloudinary_api_secret

    if not cloud or not key or not secret:
        return False

    cloudinary.config(
        cloud_name=cloud,
        api_key=key,
        api_secret=secret,
        secure=True
    )
    return True


_configured: Optional[bool] = None


def _ensure_configured() -> bool:
    global _configured
    if _configured is None:
        _configured = _configure()
        if _configured:
            logger.info("[CLOUDINARY] SDK configured successfully.")
        else:
            logger.warning("[CLOUDINARY] Missing credentials — uploads disabled.")
    return _configured


async def upload_base64(data_b64: str, resource_type: str = "image", folder: str = "karatos") -> Optional[str]:
    """
    Upload a Base64-encoded file to Cloudinary asynchronously.

    Args:
        data_b64: Raw Base64 string (no data URI prefix).
        resource_type: 'image' or 'video' (Cloudinary treats audio as video).
        folder: Cloudinary folder to organize uploads.

    Returns:
        The public secure URL, or None on failure.
    """
    if not _ensure_configured():
        return None

    try:
        import cloudinary.uploader

        # Strip data URI prefix if present (e.g. "data:image/png;base64,...")
        if "," in data_b64:
            data_b64 = data_b64.split(",", 1)[1]

        data_uri = f"data:{_mime_for(resource_type)};base64,{data_b64}"

        # Run the blocking SDK call in a thread pool
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: cloudinary.uploader.upload(
                data_uri,
                resource_type=resource_type,
                folder=folder,
                timeout=30
            )
        )

        url = result.get("secure_url")
        if url:
            logger.info(f"[CLOUDINARY] Uploaded {resource_type} → {url}")
        return url

    except Exception as e:
        logger.error(f"[CLOUDINARY] Upload failed: {e}")
        return None


def _mime_for(resource_type: str) -> str:
    if resource_type == "video":
        return "audio/webm"
    return "image/png"
