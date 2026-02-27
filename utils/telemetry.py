import json
import os
import time
from pathlib import Path
from typing import Dict, Any, List

class Telemetry:
    """
    Centralized telemetry system to track agent performance, token usage, and latency.
    """
    def __init__(self, storage_path: str = "data/telemetry.json"):
        self.storage_path = Path(storage_path)
        self.data = self._load()

    def _load(self) -> Dict[str, Any]:
        if self.storage_path.exists():
            try:
                with open(self.storage_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        
        # Default structure
        return {
            "total_tokens": 0,
            "total_interactions": 0,
            "avg_latency": 0.0,
            "start_time": time.time(),
            "history": [] # Recent latencies or token bursts for charts
        }

    def _save(self):
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.storage_path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=2)

    def record_interaction(self, tokens: int, latency: float):
        """Record a single LLM interaction."""
        self.data["total_tokens"] += tokens
        self.data["total_interactions"] += 1
        
        # Exponential moving average for latency
        if self.data["avg_latency"] == 0:
            self.data["avg_latency"] = latency
        else:
            self.data["avg_latency"] = (self.data["avg_latency"] * 0.9) + (latency * 0.1)
            
        # Add to history for charts (keep last 20)
        self.data["history"].append({
            "t": time.time(),
            "tokens": tokens,
            "latency": latency
        })
        if len(self.data["history"]) > 20:
            self.data["history"].pop(0)
            
        self._save()

    def get_stats(self) -> Dict[str, Any]:
        """Returns stats for GUI consumption."""
        return {
            "tokens": f"{self.data['total_tokens']:,}",
            "latency": f"{self.data['avg_latency']:.2f}s",
            "interactions": str(self.data["total_interactions"]),
            "uptime": self._get_uptime_str(),
            "history": self.data["history"]
        }

    def _get_uptime_str(self) -> str:
        diff = time.time() - self.data["start_time"]
        hours = int(diff // 3600)
        minutes = int((diff % 3600) // 60)
        return f"{hours}h {minutes}m"

    @staticmethod
    def estimate_tokens(text: str) -> int:
        """Rough estimation: 1 token ~= 4 characters for English/Code."""
        if not text: return 0
        return max(1, len(text) // 4)

# Singleton instance
telemetry = Telemetry()
