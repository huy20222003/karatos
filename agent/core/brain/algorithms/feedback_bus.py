"""
Phase 15.1: Neural Feedback Bus

Central signal hub enabling cross-algorithm communication and learning.
All brain algorithms emit and listen to signals through this bus,
creating a unified nervous system instead of isolated islands.

Signal Types:
  ROUTING_OUTCOME  — Was the routing decision correct? (PPF/ACR feedback)
  CORRECTION       — CIE corrected a response (Tier + reason)
  MEMORY_RECALL    — Experience memory was successfully recalled (TDM boost)
  QUERY_COMPLEXITY — NQP's complexity assessment for a query
  INTERACTION      — Full interaction summary (for reflect/metacognition)
"""
import json
import time
import threading
from collections import deque
from pathlib import Path
from typing import Optional, Any

from utils.logger import get_logger

logger = get_logger()


class NeuralSignal:
    """A single signal on the feedback bus."""
    __slots__ = ("signal_type", "data", "timestamp", "source")
    
    def __init__(self, signal_type: str, data: dict, source: str = "unknown"):
        self.signal_type = signal_type
        self.data = data
        self.timestamp = time.time()
        self.source = source
    
    def to_dict(self) -> dict:
        return {
            "type": self.signal_type,
            "data": self.data,
            "timestamp": self.timestamp,
            "source": self.source,
        }


class NeuralFeedbackBus:
    """
    Central nervous system of Brain.
    
    All algorithms emit signals here. Any algorithm can listen and react.
    Signals are kept in a ring buffer (in-memory) and optionally persisted
    to a journal file for cross-session learning.
    """
    
    # Known signal types (extensible — any string works)
    ROUTING_OUTCOME = "ROUTING_OUTCOME"
    CORRECTION = "CORRECTION"
    MEMORY_RECALL = "MEMORY_RECALL"
    QUERY_COMPLEXITY = "QUERY_COMPLEXITY"
    INTERACTION = "INTERACTION"
    
    def __init__(self, max_signals: int = 200, journal_path: str = "data/neural_journal.json"):
        self._buffer: deque[NeuralSignal] = deque(maxlen=max_signals)
        self._journal_path = Path(journal_path)
        self._lock = threading.Lock()
        self._listeners: dict[str, list] = {}  # signal_type -> [callback_fn]
        
        # Load historical journal for cross-session learning
        self._load_journal()
    
    def emit(self, signal_type: str, data: dict, source: str = "unknown"):
        """
        Emit a signal to the bus.
        
        All registered listeners for this signal_type will be notified.
        Signal is stored in ring buffer and persisted to journal.
        """
        signal = NeuralSignal(signal_type, data, source)
        
        with self._lock:
            self._buffer.append(signal)
        
        # Notify listeners
        for callback in self._listeners.get(signal_type, []):
            try:
                callback(signal)
            except Exception as e:
                logger.warning(f"[FEEDBACK] Listener error for {signal_type}: {e}")
        
        # Persist important signals
        if signal_type in (self.ROUTING_OUTCOME, self.CORRECTION, self.INTERACTION):
            self._persist_journal()
        
        logger.info(f"[FEEDBACK] 📡 Signal: {signal_type} from {source} | {self._summarize(data)}")
    
    def listen(self, signal_type: str, callback):
        """Register a callback for a specific signal type."""
        if signal_type not in self._listeners:
            self._listeners[signal_type] = []
        self._listeners[signal_type].append(callback)
    
    def get_recent(self, signal_type: Optional[str] = None, limit: int = 10) -> list[dict]:
        """Get recent signals, optionally filtered by type."""
        with self._lock:
            signals = list(self._buffer)
        
        if signal_type:
            signals = [s for s in signals if s.signal_type == signal_type]
        
        return [s.to_dict() for s in signals[-limit:]]
    
    def get_routing_accuracy(self, window: int = 50) -> dict:
        """
        Compute routing accuracy from recent ROUTING_OUTCOME signals.
        Used by ACR for weight adaptation.
        """
        outcomes = self.get_recent(self.ROUTING_OUTCOME, limit=window)
        if not outcomes:
            return {"accuracy": 0.0, "total": 0, "correct": 0}
        
        correct = sum(1 for o in outcomes if o["data"].get("was_correct", False))
        total = len(outcomes)
        
        return {
            "accuracy": correct / total,
            "total": total,
            "correct": correct,
            "ppf_bypasses": sum(1 for o in outcomes if o["data"].get("ppf_bypassed", False)),
        }
    
    def get_correction_rate(self, window: int = 50) -> dict:
        """
        Compute how often CIE needs to correct responses.
        Lower rate = better generation quality.
        """
        corrections = self.get_recent(self.CORRECTION, limit=window)
        if not corrections:
            return {"rate": 0.0, "total": 0}
        
        corrected = sum(1 for c in corrections if c["data"].get("was_corrected", False))
        return {
            "rate": corrected / len(corrections),
            "total": len(corrections),
            "corrected": corrected,
        }
    
    def get_stats(self) -> dict:
        """Get bus statistics for diagnostics."""
        with self._lock:
            total = len(self._buffer)
        
        type_counts = {}
        for sig in list(self._buffer):
            t = sig.signal_type
            type_counts[t] = type_counts.get(t, 0) + 1
        
        return {
            "total_signals": total,
            "buffer_capacity": self._buffer.maxlen,
            "type_distribution": type_counts,
            "routing_accuracy": self.get_routing_accuracy(),
            "correction_rate": self.get_correction_rate(),
        }
    
    # ========================================
    # INTERNAL
    # ========================================
    
    def _persist_journal(self):
        """Save current buffer to persistent journal (Proper JSON Array)."""
        try:
            self._journal_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._journal_path, "w", encoding="utf-8") as f:
                # We only want to persist certain signal types to keep the journal clean
                important_types = (self.ROUTING_OUTCOME, self.CORRECTION, self.INTERACTION)
                signals = [s.to_dict() for s in self._buffer if s.signal_type in important_types]
                json.dump(signals, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning(f"[FEEDBACK] Failed to persist journal: {e}")
    
    def _load_journal(self):
        """Load entries from persistent journal for cross-session context."""
        if not self._journal_path.exists():
            return
        
        try:
            if self._journal_path.stat().st_size == 0:
                logger.debug("[FEEDBACK] Journal is empty. Initializing...")
                return

            with open(self._journal_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            if not isinstance(data, list):
                logger.warning("[FEEDBACK] Journal format invalid (not a list).")
                return

            # Clear current buffer to avoid duplicates if called multiple times,
            # but usually called only in __init__
            # self._buffer.clear() 

            # Load entries into the ring buffer
            for entry in data[-self._buffer.maxlen:]:
                try:
                    sig = NeuralSignal(
                        entry.get("type", "UNKNOWN"),
                        entry.get("data", {}),
                        entry.get("source", "journal"),
                    )
                    sig.timestamp = entry.get("timestamp", time.time())
                    self._buffer.append(sig)
                except Exception:
                    continue
            
            if self._buffer:
                logger.debug(f"[FEEDBACK] Loaded {len(self._buffer)} historical signals from journal.")
        except Exception as e:
            logger.warning(f"[FEEDBACK] Failed to load journal: {e}")
    
    @staticmethod
    def _summarize(data: dict) -> str:
        """Create a brief summary of signal data for logging."""
        parts = []
        for key in ("decision", "was_correct", "tier", "confidence", "score"):
            if key in data:
                parts.append(f"{key}={data[key]}")
        return ", ".join(parts) if parts else str(data)[:80]


# ========================================
# SINGLETON
# ========================================
_instance: Optional[NeuralFeedbackBus] = None

def get_feedback_bus() -> NeuralFeedbackBus:
    global _instance
    if _instance is None:
        _instance = NeuralFeedbackBus()
    return _instance
