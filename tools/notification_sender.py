"""
Notification Sender Tool
Sends notifications across multiple channels: Telegram, Slack, Discord, generic webhooks.
"""
import asyncio
from typing import Any, Dict, Optional

from config.settings import settings
from utils.logger import get_logger

logger = get_logger()

TOOL_META = {
    "name": "notification_sender",
    "aliases": ["notify", "send_notification", "webhook"],
    "class_name": "NotificationSender",
    "description": "Notification Sender: Sends notifications via multiple channels (Telegram, Slack, Discord, webhooks).",
    "enabled": True,
    "author": "Karatos Core",
    "version": "1.0.0",
    "actions": [
        {
            "name": "send",
            "description": "Send a notification to a specified channel.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "channel": {"type": "string", "enum": ["telegram", "slack", "discord", "webhook"], "description": "Notification channel."},
                    "message": {"type": "string", "description": "Notification message."},
                    "webhook_url": {"type": "string", "description": "Webhook URL (for slack/discord/webhook channels)."},
                    "chat_id": {"type": "string", "description": "Telegram chat ID (for telegram channel)."},
                    "title": {"type": "string", "description": "Optional title/header for the notification."}
                },
                "required": ["channel", "message"]
            }
        }
    ]
}


class NotificationSender:
    """Multi-channel notification delivery."""

    @classmethod
    async def execute(cls, channel: str = "webhook", message: str = "",
                      webhook_url: str = "", chat_id: str = "",
                      title: str = "", **kwargs) -> Dict[str, Any]:
        """Send a notification to the specified channel."""
        if not message:
            return {"status": "error", "message": "Missing 'message' parameter."}

        channel = channel.lower().strip()

        if channel == "telegram":
            return await cls._send_telegram(message, chat_id, title)
        elif channel == "slack":
            return await cls._send_slack(message, webhook_url, title)
        elif channel == "discord":
            return await cls._send_discord(message, webhook_url, title)
        elif channel == "webhook":
            return await cls._send_webhook(message, webhook_url, title)
        else:
            return {"status": "error", "message": f"Unknown channel: {channel}. Supported: telegram, slack, discord, webhook."}

    @classmethod
    async def _send_telegram(cls, message: str, chat_id: str = "", title: str = "") -> Dict[str, Any]:
        """Send via Telegram Bot API."""
        bot_token = settings.telegram_bot_token
        target_chat = chat_id or settings.telegram_chat_id

        if not bot_token or not target_chat:
            return {"status": "error", "message": "Telegram not configured. Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in .env"}

        try:
            import httpx
            full_msg = f"<b>{title}</b>\n{message}" if title else message
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    f"https://api.telegram.org/bot{bot_token}/sendMessage",
                    json={"chat_id": target_chat, "text": full_msg, "parse_mode": "HTML"},
                    timeout=15.0
                )
                data = resp.json()
                if data.get("ok"):
                    logger.info(f"[NOTIFY] Telegram sent to {target_chat}")
                    return {"status": "success", "data": {"channel": "telegram", "sent_to": target_chat}}
                return {"status": "error", "message": f"Telegram API error: {data.get('description')}"}
        except Exception as e:
            return {"status": "error", "message": f"Telegram send failed: {str(e)}"}

    @classmethod
    async def _send_slack(cls, message: str, webhook_url: str = "", title: str = "") -> Dict[str, Any]:
        """Send via Slack Incoming Webhook."""
        import os
        url = webhook_url or os.getenv("SLACK_WEBHOOK_URL", "")
        if not url:
            return {"status": "error", "message": "Slack webhook URL not configured. Set SLACK_WEBHOOK_URL in .env or pass 'webhook_url'."}

        try:
            import httpx
            payload = {"text": f"*{title}*\n{message}" if title else message}
            async with httpx.AsyncClient() as client:
                resp = await client.post(url, json=payload, timeout=15.0)
                if resp.status_code == 200:
                    logger.info("[NOTIFY] Slack notification sent")
                    return {"status": "success", "data": {"channel": "slack"}}
                return {"status": "error", "message": f"Slack webhook returned {resp.status_code}"}
        except Exception as e:
            return {"status": "error", "message": f"Slack send failed: {str(e)}"}

    @classmethod
    async def _send_discord(cls, message: str, webhook_url: str = "", title: str = "") -> Dict[str, Any]:
        """Send via Discord Webhook."""
        import os
        url = webhook_url or os.getenv("DISCORD_WEBHOOK_URL", "")
        if not url:
            return {"status": "error", "message": "Discord webhook URL not configured. Set DISCORD_WEBHOOK_URL in .env or pass 'webhook_url'."}

        try:
            import httpx
            payload = {
                "embeds": [{
                    "title": title or "Notification",
                    "description": message,
                    "color": 5814783  # Blue
                }] if title else None,
                "content": message if not title else None
            }
            payload = {k: v for k, v in payload.items() if v is not None}
            async with httpx.AsyncClient() as client:
                resp = await client.post(url, json=payload, timeout=15.0)
                if resp.status_code in [200, 204]:
                    logger.info("[NOTIFY] Discord notification sent")
                    return {"status": "success", "data": {"channel": "discord"}}
                return {"status": "error", "message": f"Discord webhook returned {resp.status_code}"}
        except Exception as e:
            return {"status": "error", "message": f"Discord send failed: {str(e)}"}

    @classmethod
    async def _send_webhook(cls, message: str, webhook_url: str = "", title: str = "") -> Dict[str, Any]:
        """Send via generic webhook (POST JSON)."""
        if not webhook_url:
            return {"status": "error", "message": "Missing 'webhook_url' for generic webhook."}

        try:
            import httpx
            payload = {"title": title, "message": message, "timestamp": __import__("datetime").datetime.utcnow().isoformat()}
            async with httpx.AsyncClient() as client:
                resp = await client.post(webhook_url, json=payload, timeout=15.0)
                logger.info(f"[NOTIFY] Webhook sent to {webhook_url} ({resp.status_code})")
                return {
                    "status": "success" if resp.status_code < 400 else "error",
                    "data": {"channel": "webhook", "status_code": resp.status_code}
                }
        except Exception as e:
            return {"status": "error", "message": f"Webhook send failed: {str(e)}"}
