"""
Calendar Tool
Manages events, reminders, and schedules using local ICS storage.
"""
import os
import json
from datetime import datetime, timedelta
from typing import Any, Dict, List

from utils.logger import get_logger

logger = get_logger()

TOOL_META = {
    "name": "calendar_tool",
    "aliases": ["calendar", "schedule", "reminder", "check_reminders", "date", "time"],
    "class_name": "CalendarTool",
    "enabled": True,
    "author": "Karatos Core",
    "version": "1.0.0",
    "description": "Calendar Tool: Creates, reads, and manages events and reminders. Uses local ICS/JSON storage.",
    "actions": [
        {
            "name": "add_event",
            "description": "Create a new calendar event or reminder.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Event title."},
                    "start": {"type": "string", "description": "Start time (ISO format or natural like '2026-02-27 14:00')."},
                    "end": {"type": "string", "description": "End time. Default: 1 hour after start."},
                    "description": {"type": "string", "description": "Event description."},
                    "reminder_minutes": {"type": "integer", "description": "Reminder N minutes before. Default: 15."}
                },
                "required": ["title", "start"]
            }
        },
        {
            "name": "list_events",
            "description": "List upcoming events.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "days": {"type": "integer", "description": "Show events for the next N days. Default: 7."}
                }
            }
        },
        {
            "name": "get_current_time",
            "description": "Get the current system time and date accurately.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "timezone_offset": {"type": "integer", "description": "Optional timezone offset in hours. Default: 7 (Vietnam)."}
                }
            }
        }
    ]
}


class CalendarTool:
    """Local calendar management with JSON storage."""

    _DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "calendar")

    @classmethod
    def _ensure_dir(cls):
        os.makedirs(cls._DATA_DIR, exist_ok=True)

    @classmethod
    def _get_events_file(cls) -> str:
        cls._ensure_dir()
        return os.path.join(cls._DATA_DIR, "events.json")

    @classmethod
    def _load_events(cls) -> List[Dict]:
        path = cls._get_events_file()
        if not os.path.exists(path):
            return []
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    @classmethod
    def _save_events(cls, events: List[Dict]):
        path = cls._get_events_file()
        with open(path, "w", encoding="utf-8") as f:
            json.dump(events, f, ensure_ascii=False, indent=2, default=str)

    @classmethod
    async def execute(cls, action: str = "list_events", **params) -> Dict[str, Any]:
        """Route to calendar action."""
        if action in ["add_event", "add", "create"]:
            return await cls.add_event(**params)
        elif action in ["list_events", "list", "upcoming"]:
            return await cls.list_events(**params)
        elif action in ["check_reminders", "reminders", "check"]:
            return await cls.check_reminders(**params)
        elif action in ["delete_event", "delete", "remove"]:
            return await cls.delete_event(**params)
        elif action in ["get_current_time", "get_time", "now", "time", "date"]:
            return await cls.get_current_time(**params)
        
        # Auto-detect
        if "title" in params and "start" in params:
            return await cls.add_event(**params)
        
        # Check for time/date queries in params or intent
        if any(k in params for k in ["now", "current", "date", "time"]):
             return await cls.get_current_time(**params)
             
        return await cls.list_events(**params)

    @classmethod
    async def add_event(cls, title: str = "", start: str = "",
                        end: str = "", description: str = "",
                        reminder_minutes: int = 15, **kwargs) -> Dict[str, Any]:
        """Add a calendar event."""
        if not title or not start:
            return {"status": "error", "message": "Missing 'title' and 'start' parameters."}

        try:
            # Parse flexible datetime
            start_dt = cls._parse_datetime(start)
            end_dt = cls._parse_datetime(end) if end else start_dt + timedelta(hours=1)

            event = {
                "id": f"evt_{datetime.now().strftime('%Y%m%d%H%M%S')}",
                "title": title,
                "start": start_dt.isoformat(),
                "end": end_dt.isoformat(),
                "description": description,
                "reminder_minutes": reminder_minutes,
                "reminded": False,
                "created_at": datetime.now().isoformat()
            }

            events = cls._load_events()
            events.append(event)
            cls._save_events(events)

            logger.info(f"[CALENDAR] Event created: {title} at {start_dt}")
            return {
                "status": "success",
                "data": {
                    "event": event,
                    "message": f"Event '{title}' created for {start_dt.strftime('%Y-%m-%d %H:%M')}. Reminder will trigger {reminder_minutes} minutes before."
                }
            }
        except Exception as e:
            logger.error(f"[CALENDAR] Failed to create event: {e}")
            return {"status": "error", "message": f"Failed to create event: {str(e)}"}

    @classmethod
    async def list_events(cls, days: int = 7, **kwargs) -> Dict[str, Any]:
        """List upcoming events."""
        try:
            events = cls._load_events()
            now = datetime.now()
            cutoff = now + timedelta(days=days)

            upcoming = []
            for evt in events:
                try:
                    start = datetime.fromisoformat(evt["start"])
                    if now <= start <= cutoff:
                        upcoming.append(evt)
                except (ValueError, KeyError):
                    continue

            upcoming.sort(key=lambda e: e["start"])
            logger.info(f"[CALENDAR] Found {len(upcoming)} events in next {days} days")

            return {
                "status": "success",
                "data": {
                    "events": upcoming,
                    "count": len(upcoming),
                    "period": f"Next {days} days"
                }
            }
        except Exception as e:
            return {"status": "error", "message": f"Failed to list events: {str(e)}"}

    @classmethod
    async def check_reminders(cls, lookahead_minutes: int = 30, **kwargs) -> Dict[str, Any]:
        """
        Check for events with reminders due within the next N minutes.
        Returns events that should trigger a reminder notification.
        Called by the agent's autonomous observation cycle.
        """
        try:
            events = cls._load_events()
            now = datetime.now()
            due_reminders = []
            updated = False

            for evt in events:
                try:
                    start_dt = datetime.fromisoformat(evt["start"])
                    reminder_min = evt.get("reminder_minutes", 15)
                    already_reminded = evt.get("reminded", False)
                    
                    # Reminder trigger time = event start - reminder_minutes
                    reminder_time = start_dt - timedelta(minutes=reminder_min)
                    
                    # Is it time to remind? (within lookahead window and not yet reminded)
                    if not already_reminded and reminder_time <= now <= start_dt:
                        minutes_until = int((start_dt - now).total_seconds() / 60)
                        due_reminders.append({
                            "id": evt.get("id"),
                            "title": evt["title"],
                            "start": evt["start"],
                            "description": evt.get("description", ""),
                            "minutes_until_start": minutes_until
                        })
                        evt["reminded"] = True
                        updated = True
                except (ValueError, KeyError):
                    continue

            if updated:
                cls._save_events(events)

            return {
                "status": "success",
                "data": {
                    "due_reminders": due_reminders,
                    "count": len(due_reminders)
                }
            }
        except Exception as e:
            return {"status": "error", "message": f"Failed to check reminders: {str(e)}"}

    @classmethod
    async def delete_event(cls, event_id: str = "", title: str = "", **kwargs) -> Dict[str, Any]:
        """Delete an event by ID or title."""
        if not event_id and not title:
            return {"status": "error", "message": "Provide 'event_id' or 'title' to delete."}

        try:
            events = cls._load_events()
            original_count = len(events)
            
            events = [
                e for e in events
                if not (
                    (event_id and e.get("id") == event_id) or
                    (title and e.get("title", "").lower() == title.lower())
                )
            ]
            
            deleted = original_count - len(events)
            if deleted > 0:
                cls._save_events(events)
                return {"status": "success", "data": {"deleted_count": deleted, "message": f"Deleted {deleted} event(s)."}}
            return {"status": "success", "data": {"deleted_count": 0, "message": "No matching event found."}}
        except Exception as e:
            return {"status": "error", "message": f"Failed to delete event: {str(e)}"}

    @classmethod
    async def get_current_time(cls, timezone_offset: int = 7, **kwargs) -> Dict[str, Any]:
        """Get the current system time and date."""
        try:
            from config.settings import settings
            offset = timezone_offset or getattr(settings, 'local_timezone_offset', 7)
            # Use UTC + offset
            now = datetime.utcnow() + timedelta(hours=offset)
            
            days_vn = ["Thứ Hai", "Thứ Ba", "Thứ Tư", "Thứ Năm", "Thứ Sáu", "Thứ Bảy", "Chủ Nhật"]
            weekday_vn = days_vn[now.weekday()]
            
            return {
                "status": "success",
                "data": {
                    "timestamp": now.strftime("%Y-%m-%d %H:%M:%S"),
                    "date": now.strftime("%Y-%m-%d"),
                    "time": now.strftime("%H:%M:%S"),
                    "day_of_week": now.strftime("%A"),
                    "day_of_week_vn": weekday_vn,
                    "timezone_offset": offset,
                    "message": f"Hiện tại là {now.strftime('%H:%M:%S')}, {weekday_vn} ngày {now.strftime('%d/%m/%Y')}."
                }
            }
        except Exception as e:
            return {"status": "error", "message": f"Failed to get current time: {str(e)}"}

    @staticmethod
    def _parse_datetime(dt_str: str) -> datetime:
        """Flexibly parse datetime strings."""
        formats = [
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d %H:%M",
            "%Y-%m-%d",
            "%d/%m/%Y %H:%M",
            "%d/%m/%Y",
        ]
        for fmt in formats:
            try:
                return datetime.strptime(dt_str.strip(), fmt)
            except ValueError:
                continue
        # Last resort: ISO format
        return datetime.fromisoformat(dt_str)
