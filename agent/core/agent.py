"""
Brain Agent - Main Orchestrator
The central coordinator for all agent components.
Inspired by OpenClaw/Moltbot architecture.
"""
import asyncio
import os
from datetime import datetime
from typing import Optional, Any, Union

from config.settings import settings
from utils.logger import get_logger
from .brain import Brain
from .queue import LaneQueue, get_queue, QueuedAction
from .input_pipeline import InputPipeline, ProcessedInput
from memory.persistent import get_memory, MemoryCategory
from memory.short_term import ShortTermMemory

logger = get_logger()


class BrainAgent:
    """
    Main Agent class - orchestrates all components.
    
    Components:
    - Brain: 6-node LangGraph pipeline for reasoning
    - Queue: Lane Queue for safe action execution
    - Memory: PostgreSQL PersistentMemory for long-term storage
    - Skills: Modular skills (auto-discovered)
    - Channels: Multi-channel I/O (Telegram, etc.)
    """
    
    def __init__(self, bot_username: Optional[str] = None):
        self.bot_username = bot_username or settings.bot_username or "default_bot"
        self.base_storage_path = os.path.join("data", "storage")
        
        self.brain = Brain()
        self.queue = get_queue()
        
        # Initialize Memory with bot-specific path (Privacy Isolation)
        self.memory = get_memory(base_path=self.base_storage_path)
        
        self.short_memory = ShortTermMemory() # RAM-based short-term memory
        self.input_pipeline = InputPipeline() # Central input processor
        self.database = None  # Lazy loaded
        
        self._running = False
        self._cycle_count = 0
        self._last_patrol = None
        self._actions_this_hour = 0
        self._hour_start = datetime.utcnow()
        
        # Heartbeat intervals (seconds)
        self.patrol_interval = settings.scan_interval_minutes * 60
        
    async def initialize(self) -> bool:
        """Initialize all agent components"""
        # Ensure directory isolation exists
        os.makedirs(self.base_storage_path, exist_ok=True)

        logger.info("=" * 50)
        logger.info(f"Initializing Brain Agent: @{self.bot_username}")
        logger.info(f"Storage Path: {self.base_storage_path}")
        logger.info("=" * 50)
        
        try:
            # Initialize Brain (6-node pipeline)
            if not await self.brain.initialize():
                logger.error("Failed to initialize Brain")
                return False
            
            # Warmup Models (Parallel) - Ensures zero-wait on first request
            from core.brain.model import SharedModelProvider
            from utils.embeddings import get_embedding_engine
            
            logger.info("[WARMUP] Pre-loading models to GPU/RAM in background...")
            asyncio.create_task(SharedModelProvider.warmup())
            asyncio.create_task(get_embedding_engine().warmup())
                
            # Initialize Database
            from tools.database_reader import DatabaseReader
            self.database = DatabaseReader()
            
            # Set up queue executor
            self.queue.set_executor(self._execute_action)
            
            logger.info("All agent components initialized successfully")
            logger.info(f"Brain stats: {self.brain.get_stats()}")
            
            self._running = True  # Set to True once initialized
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize agent: {e}")
            return False
            
    async def run(self):
        """
        Main agent loop with heartbeat system.
        
        The agent continuously:
        1. Checks for incoming messages (future: Telegram, etc.)
        2. Runs patrol cycles at configured intervals
        3. Processes the action queue
        """
        if not self._running:
            self._running = True
            logger.info(f"Brain Agent @{self.bot_username} started")
            
        # Cleanup expired memories on startup
        await self.memory.cleanup_expired()
            
        # Start queue processor in background
        queue_task = asyncio.create_task(self.queue.start())
        
        try:
            while self._running:
                # Check if it's time for a patrol
                if self._should_patrol():
                    await self.patrol()
                    
                # Small sleep to prevent busy loop
                await asyncio.sleep(1)
                
        except asyncio.CancelledError:
            logger.info("Agent loop cancelled")
        finally:
            await self.queue.stop()
            queue_task.cancel()
            
    def _should_patrol(self) -> bool:
        """Check if it's time for a patrol cycle"""
        if self._last_patrol is None:
            return True
            
        elapsed = (datetime.utcnow() - self._last_patrol).total_seconds()
        return elapsed >= self.patrol_interval
        
    async def patrol(self) -> dict:
        """
        Execute a patrol cycle.
        
        This runs the full 6-node pipeline:
        OBSERVE -> REASON -> INVESTIGATE -> DECIDE -> ACT -> REFLECT
        
        Returns:
            The final state dict from the brain cycle
        """
        self._cycle_count += 1
        self._last_patrol = datetime.utcnow()
        
        logger.info("=" * 50)
        logger.info(f"PATROL CYCLE #{self._cycle_count} - {self._last_patrol.isoformat()} (@{self.bot_username})")
        logger.info("=" * 50)
        
        try:
            # Fetch audit logs
            audit_logs = self.database.get_audit_logs(
                hours=settings.rolling_window_hours,
                limit=1000
            )
            
            logger.observation(f"Retrieved {len(audit_logs)} audit log entries")
            
            # --- MEDITATION LOGIC (Idle Evolution) ---
            is_meditation = False
            if not audit_logs:
                # Every few idle cycles, trigger a meditation
                if self._cycle_count % 3 == 0:
                    logger.info("[AGENT] Triggering MEDITATION cycle (Autonomous Self-Improvement)")
                    is_meditation = True
                else:
                    logger.info("No audit logs and not meditation time. Skipping cycle.")
                    return {"decision": {"action": "IGNORE"}}
            # ----------------------------------------
                
            # Build context with persistent memory
            context = await self._build_context()
            context["database"] = self.database
            context["memory"] = self.memory
            context["is_meditation"] = is_meditation # Flag for the brain
            
            # Social awareness: inject group participant knowledge into brain context
            if hasattr(self, '_group_awareness'):
                context["group_awareness"] = self._group_awareness
                
            # Run the 6-node pipeline
            logger.info("Starting LangGraph thinking cycle...")
            final_state = await self.brain.run_cycle(audit_logs, context)
            
            # Handle decision
            if final_state.get("decision"):
                decision = final_state["decision"]
                action = decision.get("action", "IGNORE")
                
                # Check action limits
                if not self._can_take_action():
                    logger.warning("Action limit reached for this hour")
                    return final_state
                
                if action != "IGNORE":
                    # Record decision to persistent memory BEFORE executing
                    decision_id = await self.memory.record_decision(
                        target_type=decision.get("target_type", "USER"),
                        target_id=str(decision.get("target_id", "SYSTEM")),
                        action=action,
                        reason=decision.get("reason", "AI Decision"),
                        confidence=decision.get("confidence", 0) / 100.0,
                        outcome="PENDING"
                    )
                    
                    # FULLY AUTONOMOUS: Always add to queue for safe execution
                    await self.queue.add_from_decision(decision)
                    
                    # Store decision_id for later outcome update
                    if decision_id:
                        # We'll update the outcome after queue processes it
                        logger.info(f"Decision recorded with ID: {decision_id}")
                
            # Log cycle summary
            self._log_cycle_summary(final_state)
            
            # Cleanup expired memories periodically
            if self._cycle_count % 10 == 0:
                await self.memory.cleanup_expired()
                
            return final_state
            
        except Exception as e:
            logger.error(f"Patrol cycle failed: {e}")
            return {"error": str(e)}
            
    async def _build_context(self) -> dict:
        """Build context for the brain pipeline, including persistent memory"""
        context = {
            "cycle_count": self._cycle_count,
            "timestamp": datetime.utcnow().isoformat(),
            "actions_this_hour": self._actions_this_hour,
            "rolling_window_hours": settings.rolling_window_hours,
            "bot_username": self.bot_username
        }
        
        # Add database stats (optional, method may not exist)
        try:
            if hasattr(self.database, 'get_database_stats'):
                stats = self.database.get_database_stats()
                context["db_stats"] = stats
        except Exception as e:
            logger.debug(f"DB stats not available: {e}")
        
        # Add persistent memory context
        try:
            memory_context = await self.memory.get_relevant_context()
            context["recent_decisions"] = memory_context.get("recent_decisions", [])
            context["important_memories"] = memory_context.get("important_memories", [])
            context["memory_stats"] = await self.memory.get_stats()
        except Exception as e:
            logger.warning(f"Failed to get memory context: {e}")
            context["recent_decisions"] = []
            context["important_memories"] = []
            
        return context
        
    async def _execute_action(self, action: QueuedAction) -> dict:
        """
        Execute an action through the API.
        This is the queue executor callback.
        """
        logger.action(f"Executing: {action.action_type} on {action.target_type}:{action.target_id}")
        
        # Check for protected targets
        if await self._is_protected(action.target_type, action.target_id):
            logger.info(f"Skipping protected target: {action.target_id}")
            return {"success": False, "reason": "protected_target"}
            
        # Map action to API endpoint
        result = await self._call_action_api(action)
        
        if result.get("success"):
            self._actions_this_hour += 1
            
        return result
            
    async def _is_protected(self, target_type: str, target_id: str) -> bool:
        """Check if a target is protected from actions"""
        if target_type.lower() != "user":
            return False
            
        try:
            user = self.database.get_user_activity(target_id)
            if user and user.get("profile", {}).get("role") in ["ADMIN", "SUPERADMIN"]:
                logger.info(f"Protected: {target_id} is {user['profile']['role']}")
                return True
        except Exception:
            pass
            
        return False
        
    def _can_take_action(self) -> bool:
        """Check if we can take more actions this hour"""
        self._check_hourly_reset()
        return self._actions_this_hour < settings.max_actions_per_hour
        
    def _check_hourly_reset(self):
        """Reset hourly counters if needed"""
        now = datetime.utcnow()
        if (now - self._hour_start).total_seconds() >= 3600:
            self._actions_this_hour = 0
            self._hour_start = now
            
    def _log_cycle_summary(self, state: dict):
        """Log a summary of the cycle"""
        thoughts_count = len(state.get("thoughts", []))
        decision = state.get("decision", {})
        action = decision.get("action", "NONE")
        
        logger.info(f"Cycle complete. Action: {action}. Thoughts: {thoughts_count}")
        
    async def run_single_cycle(self):
        """Run a single patrol cycle (for testing)"""
        await self.patrol()
        
    async def chat(self, message: Union[str, ProcessedInput], chat_id: str, context: Optional[dict] = None) -> Optional[Union[str, dict]]:
        """
        Directly chat with the agent.
        Accepts raw string or ProcessedInput (to preserve metadata).
        """
        # 1. Handle Input Type (Preserve Metadata)
        if isinstance(message, str):
            # Fallback for direct calls without prior pipeline processing
            processed = await self.input_pipeline.process(
                message, 
                source=context.get("channel", "telegram") if context else "telegram", # Changed default source to 'telegram'
                chat_id=chat_id
            )
        else:
            processed = message

        # 2. Build context
        ctx = {
            "time": datetime.utcnow().timestamp(),
            "channel": context.get("channel", "telegram") if context else "telegram",
            "chat_id": chat_id,
            "bot_username": self.bot_username,
            "memory": self.memory,
            "short_memory": self.short_memory,
            "processed": processed # Passed into the Brain State
        }
        
        # Merge provided context (e.g. for testing)
        if context:
            ctx.update(context)
        
        # 3. Run graph-based chat
        try:
            # Note: Brain.chat will now use ctx["processed"] if available
            final_state = await self.brain.chat(processed.clean_text, chat_id, ctx)
            
            # --- NGO FIX: Handle silent offloading (None return) ---
            if final_state is None:
                return None
                
            response = final_state.get("response")
            
            # NONE classification: Brain decided this message is not for us — stay silent
            if response is None:
                return None
            
            # Standardize response to dict structure
            if isinstance(response, str):
                return {"text": response, "type": "text"}
            elif isinstance(response, dict):
                return response
            else:
                return {"text": str(response), "type": "text"}
                
        except Exception as e:
            logger.error(f"[AGENT] Chat error: {e}")
            return {"text": "I encountered a problem while processing your request.", "error": str(e)}

    async def shutdown(self):
        """Graceful shutdown of all agent components"""
        self._running = False
        logger.info("Shutting down Brain Agent...")
        
        # 1. Stop Queue (prevent new tasks)
        await self.queue.stop()
        
        # 2. Shutdown Brain (closes MCP sessions, etc.)
        await self.brain.shutdown()
        
        logger.info("Brain Agent stopped gracefully")
        
    def get_status(self) -> dict:
        """Get current agent status"""
        return {
            "running": self._running,
            "cycle_count": self._cycle_count,
            "last_patrol": self._last_patrol.isoformat() if self._last_patrol else None,
            "actions_this_hour": self._actions_this_hour,
            "queue": self.queue.get_status(),
            "memory": self.short_memory.get_summary() if self.short_memory else None,
            "brain": self.brain.get_stats() if self.brain else None,
            "bot_username": self.bot_username
        }


# Singleton instance
_agent_instance: Optional[BrainAgent] = None


def get_agent(bot_username: Optional[str] = None) -> BrainAgent:
    """Get the global agent instance"""
    global _agent_instance
    if _agent_instance is None:
        _agent_instance = BrainAgent(bot_username=bot_username)
    return _agent_instance
