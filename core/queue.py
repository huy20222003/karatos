"""
Lane Queue - Safe Action Execution
Inspired by OpenClaw's Lane Queue system.
Ensures actions are executed serially to prevent race conditions.
"""
import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Optional
from enum import Enum
import uuid

from utils.logger import get_logger

logger = get_logger()


class ActionPriority(Enum):
    """Priority levels for actions in the queue"""
    CRITICAL = 0    # Security threats - execute immediately
    HIGH = 1        # Critical alerts
    NORMAL = 2      # Regular operations
    LOW = 3         # Background tasks, reports


class ActionStatus(Enum):
    """Status of an action in the queue"""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class QueuedAction:
    """Represents an action waiting in the queue"""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    action_type: str = ""
    target_type: str = ""
    target_id: Optional[str] = None
    reason: str = ""
    priority: ActionPriority = ActionPriority.NORMAL
    status: ActionStatus = ActionStatus.PENDING
    metadata: dict = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    result: Optional[Any] = None
    error: Optional[str] = None
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "action_type": self.action_type,
            "target_type": self.target_type,
            "target_id": self.target_id,
            "reason": self.reason,
            "priority": self.priority.name,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }


class LaneQueue:
    """
    Lane Queue for safe, serial action execution.
    
    Features:
    - Serial execution (one action at a time)
    - Priority-based ordering
    - Action history tracking
    - Retry support for failed actions
    """
    
    def __init__(self, max_history: int = 100):
        self._queue: asyncio.PriorityQueue = asyncio.PriorityQueue()
        self._history: list[QueuedAction] = []
        self._max_history = max_history
        self._is_processing = False
        self._current_action: Optional[QueuedAction] = None
        self._executor: Optional[Callable] = None
        self._running = False
        
    def set_executor(self, executor: Callable):
        """Set the function that executes actions"""
        self._executor = executor
        
    async def add(
        self,
        action_type: str,
        target_type: str,
        target_id: Optional[str] = None,
        reason: str = "",
        priority: ActionPriority = ActionPriority.NORMAL,
        metadata: dict = None
    ) -> QueuedAction:
        """
        Add an action to the queue.
        
        Args:
            action_type: Type of action (ALERT, etc.)
            target_type: Type of target (user, content, etc.)
            target_id: ID of the target
            reason: Reason for the action
            priority: Priority level
            metadata: Additional data
            
        Returns:
            The queued action object
        """
        action = QueuedAction(
            action_type=action_type,
            target_type=target_type,
            target_id=target_id,
            reason=reason,
            priority=priority,
            metadata=metadata or {}
        )
        
        # Priority queue uses (priority, timestamp, action) tuple for ordering
        await self._queue.put((
            priority.value,
            action.created_at.timestamp(),
            action
        ))
        
        logger.info(f"[QUEUE] Added action: {action_type} on {target_type}:{target_id} (Priority: {priority.name})")
        return action
    
    async def add_from_decision(self, decision: dict) -> Optional[QueuedAction]:
        """
        Add an action from a brain decision dict.
        
        Args:
            decision: Decision dict from brain pipeline
            
        Returns:
            The queued action or None if decision is IGNORE
        """
        action_type = decision.get("action", "IGNORE")
        
        if action_type == "IGNORE":
            logger.info("[QUEUE] Decision is IGNORE, not queuing")
            return None
            
        # Determine priority based on action type
        priority = ActionPriority.NORMAL # Default priority
        
        if action_type in ["ESCALATE", "CRITICAL"]:
            priority = ActionPriority.HIGH
        elif action_type in ["ALERT"]:
            priority = ActionPriority.NORMAL
        elif action_type in ["NOTIFY"]:
            priority = ActionPriority.LOW
            
        return await self.add(
            action_type=action_type,
            target_type=decision.get("target_type", "user"),
            target_id=decision.get("target_id"),
            reason=decision.get("reason", ""),
            priority=priority,
            metadata=decision.get("metadata", {})
        )
    
    async def start(self):
        """Start processing the queue"""
        if self._running:
            return
            
        self._running = True
        logger.info("[QUEUE] Lane Queue started")
        
        while self._running:
            try:
                # Wait for an action with timeout
                try:
                    priority, timestamp, action = await asyncio.wait_for(
                        self._queue.get(),
                        timeout=1.0
                    )
                except asyncio.TimeoutError:
                    continue
                
                # Process the action
                if hasattr(self, "_cancelled_ids") and action.id in self._cancelled_ids:
                    logger.info(f"[QUEUE] Skipping cancelled action: {action.id}")
                    action.status = ActionStatus.CANCELLED
                    self._add_to_history(action)
                    self._cancelled_ids.remove(action.id)
                    continue

                await self._process_action(action)
                
            except Exception as e:
                logger.error(f"[QUEUE] Error in queue loop: {e}")
                await asyncio.sleep(1)
                
    async def stop(self):
        """Stop processing the queue"""
        self._running = False
        logger.info("[QUEUE] Lane Queue stopped")
        
    async def _process_action(self, action: QueuedAction):
        """Process a single action"""
        self._current_action = action
        self._is_processing = True
        action.status = ActionStatus.PROCESSING
        action.started_at = datetime.utcnow()
        
        logger.info(f"[QUEUE] Processing: {action.action_type} on {action.target_type}:{action.target_id}")
        
        try:
            if self._executor:
                result = await self._executor(action)
                action.result = result
                action.status = ActionStatus.COMPLETED
                logger.info(f"[QUEUE] Completed: {action.action_type} -> {result}")
            else:
                logger.warning("[QUEUE] No executor set, skipping action")
                action.status = ActionStatus.CANCELLED
                action.error = "No executor configured"
                
        except Exception as e:
            action.status = ActionStatus.FAILED
            action.error = str(e)
            logger.error(f"[QUEUE] Failed: {action.action_type} -> {e}")
            
        finally:
            action.completed_at = datetime.utcnow()
            self._add_to_history(action)
            self._current_action = None
            self._is_processing = False
            
    def _add_to_history(self, action: QueuedAction):
        """Add completed action to history"""
        self._history.append(action)
        
        # Trim history if too long
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history:]
            
    def get_status(self) -> dict:
        """Get queue status"""
        return {
            "is_processing": self._is_processing,
            "current_action": self._current_action.to_dict() if self._current_action else None,
            "queue_size": self._queue.qsize(),
            "history_size": len(self._history),
            "running": self._running
        }
        
    def get_history(self, limit: int = 10) -> list[dict]:
        """Get recent action history"""
        # Sort by completion time (newest first)
        history = sorted(self._history, key=lambda x: x.completed_at or x.created_at, reverse=True)
        return [a.to_dict() for a in history[:limit]]

    def get_pending(self) -> list[dict]:
        """Get list of current pending actions (visual simulation of the queue)"""
        # Priority queue doesn't expose internal list easily without 'dirty' access
        # But we can snapshot it if needed. For now, we return empty if qsize 0.
        return [] # Placeholder, PriorityQueue implementation makes this tricky
        
    async def cancel_pending(self, action_id: str) -> bool:
        """
        Cancel a pending action by ID.
        Note: Since we use asyncio.PriorityQueue, we can't easily remove items.
        We mark them as cancelled in a 'cancellation_list' and then skip them during processing.
        """
        if not hasattr(self, "_cancelled_ids"):
            self._cancelled_ids = set()
            
        self._cancelled_ids.add(action_id)
        logger.info(f"[QUEUE] Action {action_id} marked for cancellation.")
        return True


# Singleton instance
_queue_instance: Optional[LaneQueue] = None


def get_queue() -> LaneQueue:
    """Get the global queue instance"""
    global _queue_instance
    if _queue_instance is None:
        _queue_instance = LaneQueue()
    return _queue_instance
