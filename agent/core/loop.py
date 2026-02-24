"""
Autonomous Loop
The main execution loop for the agent using LangGraph Brain
Integrated with PersistentMemory for long-term storage
"""
import asyncio
from datetime import datetime
from typing import Optional

from config.settings import settings
from config.rules import AgentRules
from utils.logger import get_logger
from tools.database_reader import DatabaseReader
from memory.short_term import ShortTermMemory
from memory.context import InvestigationContext
from memory.persistent import get_memory, MemoryCategory
from .brain import Brain

logger = get_logger()


class AutonomousLoop:
    """
    The main autonomous execution loop.
    Uses LangGraph-powered Brain for intelligent decision making.
    Integrated with PostgreSQL PersistentMemory for long-term storage.
    """
    
    def __init__(self):
        self.brain = Brain()
        self.database = DatabaseReader()
        self.short_memory = ShortTermMemory()  # For in-memory cache
        self.long_memory = get_memory()        # PostgreSQL persistent memory
        self.investigations = InvestigationContext()
        self.rules = AgentRules()
        
        self._running = False
        self._cycle_count = 0
        self._actions_this_hour = 0
        self._last_hour_reset = datetime.utcnow()
    
    async def initialize(self) -> bool:
        """Initialize all components"""
        logger.info("=" * 50)
        logger.info("Initializing Brain Autonomous Agent")
        logger.info("=" * 50)
        
        # Validate settings
        try:
            settings.validate_required()
        except ValueError as e:
            logger.critical(f"Configuration error: {e}")
            return False
        
        # Initialize brain (LangGraph)
        if not await self.brain.initialize():
            logger.critical("Failed to initialize brain")
            return False
            
        # Warmup Models (Parallel) - Ensures zero-wait on first request
        from core.brain.model import SharedModelProvider
        from utils.embeddings import get_embedding_engine
        
        logger.info("[WARMUP] Pre-loading models to GPU/RAM...")
        try:
            await asyncio.gather(
                SharedModelProvider.warmup(),
                get_embedding_engine().warmup()
            )
        except Exception as e:
            logger.warning(f"[WARMUP] Non-critical warmup failure: {e}")
        
        # Test database connection
        try:
            health = self.database.get_system_health()
            breakdown = ", ".join([f"{u}: {c}" for u, c in health.get('role_breakdown', {}).items()])
            logger.info(f"Database connected: {health['total_users']} users ({breakdown})")
        except Exception as e:
            logger.critical(f"Database connection failed: {e}")
            return False
        
        logger.info("All systems initialized successfully")
        logger.info(f"Brain stats: {self.brain.get_stats()}")
        return True
    
    async def run(self):
        """Start the autonomous loop"""
        if not await self.initialize():
            logger.critical("Initialization failed. Exiting.")
            return
        
        self._running = True
        logger.info(f"Starting autonomous loop (interval: {settings.scan_interval_minutes} minutes)")
        
        # Cleanup expired memories on startup
        await self.long_memory.cleanup_expired()
        
        while self._running:
            try:
                await self._execute_cycle()
                
                # Wait for next cycle
                await asyncio.sleep(settings.scan_interval_minutes * 60)
                
            except KeyboardInterrupt:
                logger.info("Received shutdown signal")
                self._running = False
            
            except Exception as e:
                logger.error(f"Cycle error: {e}")
                await asyncio.sleep(60)  # Wait before retrying
        
        logger.info("Autonomous loop stopped")
    
    async def _execute_cycle(self):
        """Execute a single observation-decision-action cycle using LangGraph"""
        self._cycle_count += 1
        cycle_start = datetime.utcnow()
        
        logger.info(f"\n{'='*50}")
        logger.info(f"CYCLE #{self._cycle_count} - {cycle_start.isoformat()}")
        logger.info(f"{'='*50}")
        
        # Reset hourly action counter if needed
        self._check_hourly_reset()
        
        # Fetch audit logs
        audit_logs = self.database.get_audit_logs(
            hours=settings.rolling_window_hours,
            limit=1000
        )
        
        logger.observation(f"Retrieved {len(audit_logs)} audit log entries")
        
        if not audit_logs:
            logger.info("No audit logs to analyze")
            return
        
        # Store in short-term memory
        self.short_memory.add_observation({
            "type": "audit_logs",
            "count": len(audit_logs),
            "timestamp": datetime.utcnow().isoformat()
        })
        
        # Get relevant context from long-term memory
        memory_context = await self.long_memory.get_relevant_context()
        
        # Build context for brain
        context = {
            "window_hours": settings.rolling_window_hours,
            "current_time": cycle_start.isoformat(),
            "cycle_number": self._cycle_count,
            "recent_decisions": memory_context.get("recent_decisions", []),
            "important_memories": memory_context.get("important_memories", [])
        }
        
        # Run the LangGraph thinking cycle
        final_state = self.brain.run_cycle(audit_logs, context)
        
        # Process the decision from the graph
        decision = final_state.get("decision", {})
        action = decision.get("action", "IGNORE")
        
        if action != "IGNORE" and self._can_take_action():
            # Record decision to persistent memory BEFORE executing
            decision_id = await self.long_memory.record_decision(
                target_type=decision.get("target_type", "unknown"),
                target_id=decision.get("target_id", "unknown"),
                action=action,
                reason=decision.get("reason", "AI Decision"),
                confidence=decision.get("confidence", 0) / 100.0,
                outcome="PENDING"
            )
            
            # Execute the action
            success = await self._execute_action(
                action_type=action,
                target_type=decision.get("target_type", "unknown"),
                target_id=decision.get("target_id", "unknown"),
                reason=decision.get("reason", "AI Decision")
            )
            
            # Update decision outcome in persistent memory
            if decision_id:
                await self.long_memory.update_decision_outcome(
                    decision_id=decision_id,
                    outcome="SUCCESS" if success else "FAILED"
                )
        
        # Store thoughts in short-term memory
        for thought in final_state.get("thoughts", []):
            self.short_memory.add_thought(thought)
        
        # Cleanup expired memories periodically
        if self._cycle_count % 10 == 0:
            await self.long_memory.cleanup_expired()
        
        self.short_memory.cleanup_expired()
        
        cycle_duration = (datetime.utcnow() - cycle_start).total_seconds()
        logger.info(f"Cycle completed in {cycle_duration:.2f}s")
        logger.info(f"Thoughts generated: {len(final_state.get('thoughts', []))}")
    
    async def _execute_action(
        self,
        action_type: str,
        target_type: str,
        target_id: str,
        reason: str
    ) -> bool:
        """Execute an action with Self-Correction and enhanced safety."""
        # 1. Failure tracking for Self-Correction
        if not hasattr(self, "_failure_streak"):
            self._failure_streak = {}
            
        # Check if target is protected
        if target_type == "user":
            user_data = self.database.get_user_activity(target_id, hours=24)
            if user_data:
                user = user_data.get("user", {})
                if self.rules.is_user_protected(target_id, user.get("role", "")):
                    logger.info(f"Skipping protected {target_type}: {target_id}")
                    return False
        
        # Check cooldown in short-term memory (Use setting)
        cooldown = getattr(settings, "action_cooldown_minutes", 60)
        if self.short_memory.is_on_cooldown(action_type, target_id, cooldown_minutes=cooldown):
            logger.info(f"Skipping {target_id} - on cooldown")
            return False
        
        # ... logic for user warning history ...
        
        logger.action(f"Executing {action_type} on {target_type}:{target_id}")
        
        # Execution through API is deprecated.
        logger.info(f"Action execution through API Client is deprecated and removed for: {action_type}")
        success = False
        
        # 2. SELF-CORRECTION LOGIC
        if not success:
            key = f"{action_type}:{target_id}"
            self._failure_streak[key] = self._failure_streak.get(key, 0) + 1
            if self._failure_streak[key] >= 3:
                logger.warning(f"[SELF-HEALING] Action {key} failed 3 times. Triggering Architectural Review...")
                # Trigger a high-priority system goal for the next cycle
                self.short_memory.add_thought(f"SYSTEM_ALERT: Action {key} is failing consistently. I need to re-evaluate the API path or permission logic.")
        else:
            # Reset streak on success
            self._failure_streak.pop(f"{action_type}:{target_id}", None)

        if response:
            logger.result(response.success, f"{action_type}: {response.error or 'Success'}")
            self._actions_this_hour += 1
            self.short_memory.add_action(action_type, target_id, {"reason": reason})
        
        return success
    
    def _can_take_action(self) -> bool:
        """Check if we're within action limits"""
        return self._actions_this_hour < settings.max_actions_per_hour
    
    def _check_hourly_reset(self):
        """Reset hourly counters if needed"""
        now = datetime.utcnow()
        if (now - self._last_hour_reset).total_seconds() >= 3600:
            self._actions_this_hour = 0
            self._last_hour_reset = now
            logger.debug("Hourly action counter reset")
    
    def stop(self):
        """Stop the autonomous loop"""
        self._running = False
        logger.info("Stop signal received")
    
    def get_status(self) -> dict:
        """Get current agent status"""
        return {
            "running": self._running,
            "cycle_count": self._cycle_count,
            "actions_this_hour": self._actions_this_hour,
            "max_actions_per_hour": settings.max_actions_per_hour,
            "memory": self.short_memory.get_summary(),
            "investigations": self.investigations.get_statistics(),
            "brain": self.brain.get_stats()
        }

