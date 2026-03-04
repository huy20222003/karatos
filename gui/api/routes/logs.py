"""
Logs API Routes — Read agent log files.
"""
import os
from datetime import datetime
from fastapi import APIRouter, Query

router = APIRouter()


@router.get("")
async def get_logs(
    lines: int = Query(200, ge=10, le=1000),
    level: str = Query("ALL", description="Filter by log level: ALL, DEBUG, INFO, WARNING, ERROR"),
):
    """Tail the current day's log file."""
    from config.settings import settings

    log_dir = settings.log_dir
    date_str = datetime.now().strftime("%Y-%m-%d")
    log_file = os.path.join(log_dir, f"agent-{date_str}.log")

    if not os.path.exists(log_file):
        return {"entries": [], "file": log_file, "error": "Log file not found"}

    try:
        with open(log_file, "r", encoding="utf-8") as f:
            all_lines = f.readlines()

        # Take last N lines
        tail = all_lines[-lines:]

        entries = []
        for line in tail:
            line = line.strip()
            if not line:
                continue

            # Parse: "2026-03-04 12:09:39 | INFO     | Brain | [GUI] ..."
            entry = _parse_log_line(line)
            if entry:
                if level != "ALL" and entry["level"] != level:
                    continue
                entries.append(entry)

        return {"entries": entries, "file": os.path.basename(log_file), "total_lines": len(all_lines)}
    except Exception as e:
        return {"entries": [], "file": log_file, "error": str(e)}


def _parse_log_line(line: str) -> dict:
    """Parse a log line into structured data."""
    try:
        # Format: "YYYY-MM-DD HH:MM:SS | LEVEL    | Name | message"
        parts = line.split(" | ", 3)
        if len(parts) >= 3:
            timestamp = parts[0].strip()
            level = parts[1].strip()
            rest = parts[2] if len(parts) == 3 else parts[3]
            return {
                "timestamp": timestamp,
                "level": level,
                "message": rest.strip(),
            }
    except Exception:
        pass
    # Fallback: unparseable line
    return {"timestamp": "", "level": "INFO", "message": line}
