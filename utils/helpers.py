import os
import functools
import time
import json
import hashlib
from pathlib import Path
from datetime import datetime, timedelta
from typing import Any, Optional, Callable, Dict, Union

def retry(max_attempts: int = 3, delay: float = 1.0, backoff: float = 2.0, exceptions: tuple = (Exception,)):
    """
    Retry decorator with exponential backoff.
    """
    def decorator(func: Callable):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            attempts = 0
            current_delay = delay
            while attempts < max_attempts:
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    attempts += 1
                    if attempts >= max_attempts:
                        raise e
                    from utils.logger import get_logger
                    logger = get_logger()
                    logger.warning(f"[RETRY] Attempt {attempts}/{max_attempts} for {func.__name__} failed: {e}. Retrying in {current_delay}s...")
                    time.sleep(current_delay)
                    current_delay *= backoff
            return None
        return wrapper
    return decorator


def format_timestamp(dt: Union[datetime, str], fmt: str = "%Y-%m-%d %H:%M:%S") -> str:
    """Format a datetime object OR string to a standard string format"""
    if isinstance(dt, str):
        parsed = parse_timestamp(dt)
        return parsed.strftime(fmt) if parsed else dt
    return dt.strftime(fmt)


def safe_timestamp_convert(val: Any) -> datetime:
    """Safely convert any value (str, float, int) to datetime"""
    if isinstance(val, datetime):
        return val
    if isinstance(val, (int, float)):
        return datetime.fromtimestamp(val)
    if isinstance(val, str):
        parsed = parse_timestamp(val)
        return parsed if parsed else datetime.utcnow()
    return datetime.utcnow()


def resolve_path(path_str: str) -> Path:
    """
    Resolve a path relative to the project root.
    If path is absolute, returns it as Path object.
    """
    path = Path(path_str)
    if path.is_absolute():
        return path
    
    # Assuming app root is one level up from utils/
    root_dir = Path(__file__).parent.parent
    return root_dir / path_str


def parse_timestamp(timestamp_str: str) -> Optional[datetime]:
    """Parse a timestamp string to datetime"""
    formats = [
        "%Y-%m-%dT%H:%M:%S.%fZ",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
    ]
    
    for fmt in formats:
        try:
            return datetime.strptime(timestamp_str, fmt)
        except ValueError:
            continue
    
    return None


def get_time_window(hours: int = 3) -> tuple[datetime, datetime]:
    """
    Get start and end datetime for a rolling time window.
    Returns (start_time, end_time) where end_time is now.
    """
    end_time = datetime.utcnow()
    start_time = end_time - timedelta(hours=hours)
    return start_time, end_time


def truncate_text(text: str, max_length: int = 500, suffix: str = "...") -> str:
    """Truncate text to a maximum length"""
    if len(text) <= max_length:
        return text
    return text[:max_length - len(suffix)] + suffix


def safe_json_parse(data: str, default: Any = None) -> Any:
    """Safely parse JSON string, return default on error"""
    try:
        return json.loads(data)
    except (json.JSONDecodeError, TypeError):
        return default


def safe_json_dumps(data: Any, indent: int = None) -> str:
    """Safely serialize object to JSON string, with bytes→base64 support"""
    import base64
    from uuid import UUID
    from datetime import datetime, date

    class SafeEncoder(json.JSONEncoder):
        def default(self, obj):
            # Try Pydantic model_dump or dict
            if hasattr(obj, "model_dump") and callable(obj.model_dump):
                return obj.model_dump()
            if hasattr(obj, "dict") and callable(obj.dict):
                return obj.dict()
                
            if isinstance(obj, bytes):
                b64 = base64.b64encode(obj).decode('utf-8')
                return f"data:image/png;base64,{b64}"
            if isinstance(obj, UUID):
                return str(obj)
            if isinstance(obj, (datetime, date)):
                return obj.isoformat()
            
            # Fallback to string representation cautiously
            try:
                return super().default(obj)
            except TypeError:
                return str(obj)

    try:
        return json.dumps(data, indent=indent, cls=SafeEncoder, ensure_ascii=False)
    except (TypeError, ValueError):
        return "{}"


def calculate_anomaly_score(current_value: float, baseline: float, std_dev: float = 1.0) -> float:
    """
    Calculate anomaly score based on deviation from baseline.
    Returns a score between 0 and 1, where 1 is highly anomalous.
    """
    if std_dev == 0:
        return 0.0 if current_value == baseline else 1.0
    
    deviation = abs(current_value - baseline) / std_dev
    # Normalize using sigmoid-like function
    score = min(1.0, deviation / 3)  # 3 std devs = score of 1.0
    return round(score, 3)


def group_by_key(items: list[dict], key: str) -> dict[str, list[dict]]:
    """Group a list of dictionaries by a specific key"""
    result = {}
    for item in items:
        key_value = str(item.get(key, "unknown"))
        if key_value not in result:
            result[key_value] = []
        result[key_value].append(item)
    return result


def count_occurrences(items: list[dict], key: str) -> dict[str, int]:
    """Count occurrences of each value for a given key"""
    counts = {}
    for item in items:
        value = str(item.get(key, "unknown"))
        counts[value] = counts.get(value, 0) + 1
    return counts


def mask_sensitive_data(data: str, visible_chars: int = 4) -> str:
    """Mask sensitive data for logging (like email, ID)"""
    if len(data) <= visible_chars:
        return "*" * len(data)
    return data[:visible_chars] + "*" * (len(data) - visible_chars)


import time
from contextlib import contextmanager

@contextmanager
def task_timer(name: str):
    """
    Context manager to time a task.
    """
    start = time.perf_counter()
    from utils.logger import get_logger
    logger = get_logger()
    try:
        yield
    finally:
        elapsed = time.perf_counter() - start
        logger.info(f"[PERF] {name} took {elapsed:.3f}s")


def memoize(func: Callable):
    """Simple in-memory cache decorator for expensive functions"""
    cache = {}
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        # Create a stable key from arguments
        key = f"{func.__name__}:{hashlib.md5(str(args).encode()).hexdigest()}:{hashlib.md5(str(kwargs).encode()).hexdigest()}"
        if key not in cache:
            cache[key] = func(*args, **kwargs)
        return cache[key]
    return wrapper
