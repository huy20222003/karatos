"""
Choice Detector Utility
Analyzes assistant answers to detect when they are asking the user
to choose between concrete options, and returns a UI-ready payload.
"""
from typing import Any, Dict, List, Optional, Union
import logging

from config.settings import settings
from core.brain.model import SharedModelProvider
from core.brain.prompts.registry import get_prompt_registry
from core.brain.utils import extract_json, get_llm_content

logger = logging.getLogger(__name__)


async def detect_choices(
    answer_text: str,
    user_message: str,
    language: str = "vi",
) -> Dict[str, Any]:
    """
    Ask the Brain to decide whether this answer is a choice prompt
    and, if so, extract structured options.
    """
    if not answer_text or not user_message:
        return {"is_choice": False, "style": "none", "options": []}

    try:
        model = SharedModelProvider.get_model()
        registry = get_prompt_registry()

        # Normalize language descriptor for the prompt.
        lang_desc = "Vietnamese" if language == "vi" else "English"

        prompt = registry.get(
            "system.choices.choices_detect",
            user_message=user_message,
            answer=answer_text,
            language=lang_desc,
        )

        raw = await model.think(prompt, phase="brief")
        content = get_llm_content(raw)
        data = extract_json(content)
        if not isinstance(data, dict):
            raise ValueError("Choice detector did not return a JSON object")

        # Basic normalization
        is_choice = bool(data.get("is_choice"))
        style = str(data.get("style") or "none")
        options = data.get("options") or []
        if not isinstance(options, list):
            options = []

        normalized_options: List[Dict[str, str]] = []
        for opt in options:
            if not isinstance(opt, dict):
                continue
            oid = str(opt.get("id") or "").strip()
            label = str(opt.get("label") or oid).strip()
            value = str(opt.get("value") or oid).strip()
            if not oid or not label:
                continue
            normalized_options.append({"id": oid, "label": label, "value": value})

        if not is_choice or not normalized_options:
            return {"is_choice": False, "style": "none", "options": []}

        return {"is_choice": True, "style": style, "options": normalized_options}

    except Exception as e:
        logger.warning(f"[CHOICE_DETECTOR] Detection failed: {e}")
        return {"is_choice": False, "style": "none", "options": []}


async def enhance_response_for_telegram(
    response: Union[str, Dict[str, Any]],
    *,
    user_message: str,
    language: str = "vi",
) -> Union[str, Dict[str, Any]]:
    """
    If the assistant answer is a choice prompt, enrich it with Telegram
    inline keyboard buttons. Otherwise, return the original response.
    """
    # Extract plain text from the response
    if isinstance(response, dict):
        answer_text = str(response.get("text") or response.get("caption") or "")
    else:
        answer_text = str(response)

    detection = await detect_choices(answer_text=answer_text, user_message=user_message, language=language)
    if not detection.get("is_choice") or detection.get("style") != "buttons":
        return response

    options = detection.get("options", [])
    if not options:
        return response

    # Build Telegram inline keyboard (one row with up to 3 buttons per row).
    keyboard_rows: List[List[Dict[str, str]]] = []
    row: List[Dict[str, str]] = []
    for opt in options:
        if len(row) >= 3:
            keyboard_rows.append(row)
            row = []
        callback_data = f"choice:{opt['id']}"
        row.append({"text": opt["label"], "callback_data": callback_data})
    if row:
        keyboard_rows.append(row)

    inline_keyboard = {"inline_keyboard": keyboard_rows}

    # Normalize response to dict payload for TelegramChannel
    if isinstance(response, str):
        return {"text": response, "keyboard": inline_keyboard}

    enriched = dict(response)
    # Merge or override existing keyboard
    existing_keyboard = enriched.get("keyboard")
    if existing_keyboard and isinstance(existing_keyboard, dict):
        # Append our rows to existing keyboard if both use inline style
        rows = existing_keyboard.get("inline_keyboard") or []
        if isinstance(rows, list):
            rows.extend(keyboard_rows)
            existing_keyboard["inline_keyboard"] = rows
            enriched["keyboard"] = existing_keyboard
        else:
            enriched["keyboard"] = inline_keyboard
    else:
        enriched["keyboard"] = inline_keyboard

    return enriched

