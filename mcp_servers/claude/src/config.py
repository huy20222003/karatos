import os
import re
import secrets
import uuid
from typing import Dict


BASE_URL: str = os.getenv("CLAUDE_BASE_URL", "https://claude.ai/api")

# Required cookie copied from browser (must contain lastActiveOrg)
CLAUDE_DIRECT_COOKIE_ENV: str = "CLAUDE_DIRECT_COOKIE"

DEFAULT_MODEL: str = os.getenv("CLAUDE_DEFAULT_MODEL", "claude-sonnet-4-6")

# Dynamically generate client identifiers for this server process
CLAUDE_CLIENT_SHA: str = secrets.token_hex(20)
CLAUDE_DEVICE_ID: str = str(uuid.uuid4())
CLAUDE_ANONYMOUS_ID: str = f"claudeai.v1.{uuid.uuid4()}"


def get_cookie() -> str:
    cookie = os.getenv(CLAUDE_DIRECT_COOKIE_ENV)
    if not cookie:
        raise RuntimeError(
            f"{CLAUDE_DIRECT_COOKIE_ENV} is not set. "
            "Set it to the claude.ai session cookie string that contains lastActiveOrg=...."
        )
    return cookie


def extract_org_id(cookie: str) -> str:
    if not cookie:
        raise RuntimeError("Claude Direct cookie is empty.")
    match = re.search(r"lastActiveOrg=([^;]+)", cookie)
    if not match:
        raise RuntimeError("Could not find lastActiveOrg in CLAUDE_DIRECT_COOKIE.")
    return match.group(1)


def build_headers(cookie: str) -> Dict[str, str]:
    return {
        "accept": "text/event-stream, text/event-stream",
        "accept-language": "vi-VN,vi;q=0.9,fr-FR;q=0.8,fr;q=0.7,en-US;q=0.6,en;q=0.5",
        "anthropic-anonymous-id": CLAUDE_ANONYMOUS_ID,
        "anthropic-client-platform": "web_claude_ai",
        "anthropic-client-sha": CLAUDE_CLIENT_SHA,
        "anthropic-client-version": "1.0.0",
        "anthropic-device-id": CLAUDE_DEVICE_ID,
        "content-type": "application/json",
        "cookie": cookie,
        "origin": "https://claude.ai",
        "priority": "u=1, i",
        "referer": "https://claude.ai/new",
        "sec-ch-ua": '"Not(A:Brand";v="8", "Chromium";v="144", "Google Chrome";v="144"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "user-agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/144.0.0.0 Safari/537.36"
        ),
    }

