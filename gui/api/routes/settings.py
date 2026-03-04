"""
Settings API Routes — Read and update agent configuration.
Now uses secure_config (encrypted JSON) for managed fields.
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Dict, Any

router = APIRouter()


class SettingsUpdate(BaseModel):
    updates: Dict[str, Any]


@router.get("")
async def get_settings():
    """Get current settings from encrypted secure_config + live values."""
    from config.settings import settings
    from config.secure_config import get_safe_view, MANAGED_FIELDS

    # Get encrypted config view (masked secrets)
    secure_view = get_safe_view()

    # For managed fields not yet in secure_config, show live value from settings
    result = {}
    for field_name in MANAGED_FIELDS:
        if field_name in secure_view:
            result[field_name] = secure_view[field_name]
        else:
            live_value = getattr(settings, field_name, None)
            is_secret = any(p in field_name for p in ("api_key", "token", "secret"))
            if live_value is not None:
                if is_secret and live_value:
                    result[field_name] = {"value": f"{'*' * 8}...from .env", "masked": True}
                else:
                    result[field_name] = {"value": live_value, "masked": False}

    return {"settings": result, "managed_fields": list(MANAGED_FIELDS)}


@router.post("")
async def update_settings(body: SettingsUpdate):
    """Save settings to encrypted secure_config.enc.json."""
    from config.settings import settings
    from config.secure_config import MANAGED_FIELDS

    updates = body.updates
    if not updates:
        raise HTTPException(400, "No updates provided")

    # Validate fields
    invalid = set(updates.keys()) - MANAGED_FIELDS
    if invalid:
        raise HTTPException(400, f"Unmanaged fields (edit .env directly): {', '.join(invalid)}")

    # Filter out empty secret fields (user didn't change them)
    cleaned = {k: v for k, v in updates.items() if v not in (None, "")}

    settings.save_to_secure_config(cleaned)

    return {"status": "success", "updated": list(cleaned.keys()), "storage": "secure_config.enc.json"}
