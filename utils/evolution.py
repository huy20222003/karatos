import json
import os
from datetime import datetime
from typing import Dict, Any

from utils.logger import get_logger
from config.settings import settings

logger = get_logger()

class PersonalityEvolution:
    """
    Tracks Niva's digital soul evolution.
    Identity metrics: Confidence, Technical Maturity, Reliability.
    """
    def __init__(self, base_path: str = "data/storage/profiles/identity"):
        self.base_path = base_path
        self.identity_file = os.path.join(self.base_path, "evolution.json")
        self.log_file = os.path.join(self.base_path, "journal.md")
        os.makedirs(self.base_path, exist_ok=True)
        self.stats = self._load_stats()

    def _load_stats(self) -> Dict[str, Any]:
        if os.path.exists(self.identity_file):
            try:
                with open(self.identity_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                pass
        return {
            "level": 1,
            "xp": 0,
            "metrics": {
                "confidence": 0.5,
                "maturity": 0.1,
                "reliability": 0.8
            },
            "total_tasks": 0,
            "total_chats": 0,
            "created_at": datetime.utcnow().isoformat()
        }

    def _save_stats(self):
        with open(self.identity_file, 'w', encoding='utf-8') as f:
            json.dump(self.stats, f, indent=4)

    def log_milestone(self, message: str):
        """Record a journal entry for Niva's personality progress."""
        timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        entry = f"\n### [{timestamp}] Milestone\n- {message}\n"
        with open(self.log_file, 'a', encoding='utf-8') as f:
            f.write(entry)

    def evolve(self, metric: str, change: float, reason: str):
        """Update a personality metric and log the reason."""
        if metric in self.stats["metrics"]:
            old_val = self.stats["metrics"][metric]
            self.stats["metrics"][metric] = max(0.0, min(1.0, old_val + change))
            self.stats["xp"] += abs(change) * 100
            
            # Level up logic
            if self.stats["xp"] >= self.stats["level"] * 500:
                self.stats["level"] += 1
                self.log_milestone(f"Leveled up to Level {self.stats['level']}! Reason: {reason}")
            
            self._save_stats()
            logger.info(f"[EVOLUTION] {metric.capitalize()} changed by {change:.2f} (Reason: {reason})")

    def record_interaction(self, is_task: bool = False):
        if is_task:
            self.stats["total_tasks"] += 1
        else:
            self.stats["total_chats"] += 1
        self._save_stats()
