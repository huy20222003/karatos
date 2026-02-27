from typing import Optional, Tuple
import uuid

import httpx

from .config import BASE_URL, DEFAULT_MODEL, build_headers, extract_org_id, get_cookie


async def create_conversation(client: httpx.AsyncClient, headers: dict, org_id: str) -> str:
    url = f"{BASE_URL}/organizations/{org_id}/chat_conversations"
    payload = {
        "uuid": str(uuid.uuid4()),
        "name": "",
        "include_conversation_preferences": True,
        "is_temporary": False,
    }
    resp = await client.post(url, json=payload, headers=headers, timeout=30.0)
    resp.raise_for_status()
    data = resp.json()
    conv_id = data.get("uuid")
    if not conv_id:
        raise RuntimeError("Claude create_conversation response missing uuid.")
    return conv_id


async def send_message(prompt: str, model: Optional[str] = None) -> Tuple[str, str]:
    """
    Send a prompt to Claude.ai web endpoint and return (content, finish_reason).
    This function mimics the original Node.js Claude Direct behavior.
    """
    cookie = get_cookie()
    org_id = extract_org_id(cookie)
    headers = build_headers(cookie)
    model_name = model or DEFAULT_MODEL

    async with httpx.AsyncClient(timeout=None) as client:
        conversation_uuid = await create_conversation(client, headers, org_id)

        url = (
            f"{BASE_URL}/organizations/{org_id}/chat_conversations/"
            f"{conversation_uuid}/completion"
        )

        payload = {
            "prompt": prompt,
            "parent_message_uuid": "00000000-0000-4000-8000-000000000000",
            "timezone": "UTC",
            "personalized_styles": [],
            "locale": "en-US",
            "model": model_name,
            "tools": [],
            "attachments": [],
            "files": [],
            "sync_sources": [],
            "rendering_mode": "messages",
        }

        full_text = ""
        finish_reason = "stop"

        async with client.stream("POST", url, headers=headers, json=payload) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line or not line.startswith("data:"):
                    continue
                data_str = line[5:].strip()
                if not data_str:
                    continue
                try:
                    event = httpx.Response(200, text=data_str).json()
                except Exception:
                    # Heartbeats or partial JSON chunks can be ignored safely
                    continue

                event_type = event.get("type")
                if event_type == "content_block_delta":
                    delta = event.get("delta") or {}
                    text_piece = delta.get("text")
                    if text_piece:
                        full_text += text_piece
                elif event_type == "message_stop":
                    finish_reason = "stop"

        return full_text.strip(), finish_reason

