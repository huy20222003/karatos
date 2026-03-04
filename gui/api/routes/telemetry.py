"""
Telemetry API Routes — Agent performance metrics and history.
"""
import json
import os
import time
from fastapi import APIRouter

router = APIRouter()

_TELEMETRY_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "..", "data", "telemetry.json")


def _load_telemetry() -> dict:
    """Load telemetry data from JSON file."""
    try:
        path = os.path.normpath(_TELEMETRY_PATH)
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {"total_tokens": 0, "total_interactions": 0, "avg_latency": 0, "start_time": time.time(), "history": []}


@router.get("/summary")
async def get_telemetry_summary():
    """Summary stats: total tokens, interactions, avg latency, uptime."""
    data = _load_telemetry()
    start_time = data.get("start_time", time.time())
    uptime_seconds = time.time() - start_time

    # Calculate tokens/minute rate
    tokens_per_min = 0
    if uptime_seconds > 0:
        tokens_per_min = data.get("total_tokens", 0) / (uptime_seconds / 60)

    return {
        "total_tokens": data.get("total_tokens", 0),
        "total_interactions": data.get("total_interactions", 0),
        "avg_latency": round(data.get("avg_latency", 0), 2),
        "uptime_seconds": round(uptime_seconds),
        "tokens_per_minute": round(tokens_per_min, 1),
        "start_time": start_time,
    }


@router.get("/history")
async def get_telemetry_history():
    """Time-series history for charts (tokens + latency per interaction)."""
    data = _load_telemetry()
    history = data.get("history", [])

    # Return last 50 entries for charting
    entries = history[-50:]

    return {
        "entries": [
            {
                "timestamp": e.get("t", 0),
                "tokens": e.get("tokens", 0),
                "latency": round(e.get("latency", 0), 2),
            }
            for e in entries
        ],
        "total_entries": len(history),
    }
