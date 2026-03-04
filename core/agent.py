"""
Brain Agent - Main Orchestrator
The central coordinator for all agent components.
Inspired by OpenClaw/Moltbot architecture.
"""
import asyncio
import os
from datetime import datetime
from typing import Optional, Any, Union

from config.secure_config import CONFIG_PATH
from config.settings import settings
from utils.logger import get_logger
from utils.config_watcher import start_config_watcher
from core.brain import Brain
from core.queue import LaneQueue, get_queue, QueuedAction
from core.input_pipeline import InputPipeline, ProcessedInput
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
        logger.debug("[AGENT] Starting BrainAgent constructor...")
        self.bot_username = bot_username or settings.bot_username or "default_bot"
        self.base_storage_path = os.path.join("data", "storage")
        
        logger.debug("[AGENT] Instantiating Brain and LaneQueue...")
        self.brain = Brain()
        self.queue = get_queue()
        logger.debug("[AGENT] BrainAgent object created.")
        
        # Initialize Memory with bot-specific path (Privacy Isolation)
        self.memory = get_memory(base_path=self.base_storage_path)
        
        self.short_memory = ShortTermMemory() # RAM-based short-term memory
        self.input_pipeline = InputPipeline() # Central input processor
        self.database = None  # Lazy loaded
        self._universal_config_observer = None # Universal config watcher
        
        self._running = False
        self._cycle_count = 0
        self._last_patrol = None
        self._last_patrol_time = datetime.utcnow() # Initialize to now to avoid immediate patrol
        self._actions_this_hour = 0
        self._hour_start = datetime.utcnow()
        
        # Live mood/energy (updated after each brain cycle)
        self._last_mood = "OPTIMISTIC"
        self._last_energy = 1.0
        
        # Heartbeat intervals (seconds)
        self.patrol_interval = settings.scan_interval_minutes * 60
        
    async def initialize(self) -> bool:
        """Initialize all agent components"""
        logger.debug("[AGENT] Starting initialize()...")
        # Ensure directory isolation exists
        os.makedirs(self.base_storage_path, exist_ok=True)

        logger.info("=" * 50)
        logger.info(f"Initializing Brain Agent: @{self.bot_username}")
        logger.info(f"Storage Path: {self.base_storage_path}")
        logger.info("=" * 50)
        
        try:
            # Initialize Brain (6-node pipeline)
            logger.debug("[AGENT] Initializing Brain components...")
            if not await self.brain.initialize():
                logger.error("Failed to initialize Brain")
                return False
            
            # Warmup Models (Parallel) - Ensures zero-wait on first request
            from core.brain.model import SharedModelProvider
            from utils.embeddings import get_embedding_engine
            
            logger.info("[WARMUP] Pre-loading models to GPU/RAM in background...")
            logger.debug("[AGENT] Spawning model warmup task...")
            asyncio.create_task(SharedModelProvider.warmup())
            logger.debug("[AGENT] Spawning embedding warmup task...")
            asyncio.create_task(get_embedding_engine().warmup())
                
            # Initialize Database
            logger.debug("[AGENT] Initializing DatabaseReader...")
            from tools.database_reader import DatabaseReader
            self.database = DatabaseReader()
            
            # Set up queue executor
            logger.debug("[AGENT] Setting up queue executor...")
            self.queue.set_executor(self._execute_action)
            
            logger.info("All agent components initialized successfully")
            logger.info(f"Brain stats: {self.brain.get_stats()}")
            
            # Start universal config watcher for auto-reload (Monitoring entire config/ directory)
            try:
                config_dir = os.path.dirname(CONFIG_PATH)
                self._universal_config_observer = start_config_watcher(config_dir, self.reload_system, is_directory=True)
            except Exception as e:
                logger.warning(f"[AGENT] Failed to start universal config watcher: {e}")
            
            self._running = True  # Set to True once initialized
            logger.debug("[AGENT] initialize() complete.")
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize agent: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False
            
    def refresh_identity(self):
        """Update agent identity from settings (called after channel connection)"""
        old_username = self.bot_username
        self.bot_username = settings.bot_username or "default_bot"
        if old_username != self.bot_username:
            logger.info(f"[AGENT] Identity binding updated: @{old_username} -> @{self.bot_username}")

    def reload_system(self):
        """Universal reload for all agent components based on config changes."""
        logger.info("[AGENT] 🔄 Universal Config Change Detected. Reloading system...")
        try:
            # 1. Reload main settings
            settings.load_from_secure_config()
            
            # 2. Reload MCP Bridge
            from tools.mcp_bridge import get_mcp_bridge
            get_mcp_bridge().reload()
            
            # 3. Clear LLM cache
            from core.brain.model import SharedModelProvider
            SharedModelProvider.clear_cache()
            
            # 4. Update runtime params
            self.patrol_interval = settings.scan_interval_minutes * 60
            self.refresh_identity()
            
            logger.info("[AGENT] ✅ System reloaded and synchronized successfully.")
        except Exception as e:
            logger.error(f"[AGENT] ❌ Universal reload failed: {e}")
            
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
            
            # --- ORGANIC CALENDAR CHECK (Memory Injection) ---
            try:
                from tools.calendar_tool import CalendarTool
                # Using a 30-minute lookahead to give the agent time to prepare
                calendar_res = await CalendarTool.check_reminders(lookahead_minutes=30)
                
                if calendar_res.get("status") == "success":
                    due_reminders = calendar_res.get("data", {}).get("due_reminders", [])
                    
                    for reminder in due_reminders:
                        # Synthesize an internal event
                        audit_logs.append({
                            "id": reminder.get("id", f"c_{self._cycle_count}"),
                            "event_type": "INTERNAL_URGE",
                            "status": "warning", # Flag as warning so decider pays attention
                            "message": f"[CALENDAR REMINDER] It is time for event: '{reminder.get('title')}'. Expected Time: {reminder.get('start')}. Description: {reminder.get('description', '')}. I MUST fulfill this now.",
                            "target_id": "System",
                            "timestamp": datetime.utcnow().isoformat()
                        })
                        
                    if due_reminders:
                        logger.info(f"[CALENDAR] Injected {len(due_reminders)} calendar reminders into the agent's subconscious.")
            except Exception as e:
                logger.error(f"[CALENDAR] Failed to process calendar reminders: {e}")
                
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
            
            # Track mood/energy for dashboard
            self._last_mood = final_state.get("mood", self._last_mood)
            self._last_energy = final_state.get("energy_level", self._last_energy)
            
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
                    
                    # Attach decision_id to queued action metadata so outcomes can be persisted.
                    if decision_id:
                        meta = decision.get("metadata") or {}
                        meta["decision_id"] = decision_id
                        decision["metadata"] = meta

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

        # Persist outcome back to decision history if available.
        try:
            decision_id = (action.metadata or {}).get("decision_id")
            if decision_id:
                outcome = "SUCCESS" if result.get("success") else "FAILED"
                await self.memory.update_decision_outcome(decision_id, outcome)
        except Exception as e:
            logger.debug(f"[MEMORY] Failed to persist decision outcome: {e}")
            
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
            # --- NGO FIX: Record User Message (Start of cycle) ---
            episode_id = ctx.get("episode_id") or f"ep_{int(datetime.utcnow().timestamp())}"
            ctx["episode_id"] = episode_id # Ensure it's in context for Brain
            
            user_meta = {}
            if context:
                # Only persist distilled text knowledge — never raw media references.
                # The Distiller will synthesize insights from the full conversation.
                if context.get("audio_transcript"):
                    user_meta["audio_transcript"] = context["audio_transcript"]
                
            await self.memory.record_chat_message(chat_id, "user", processed.clean_text, episode_id=episode_id, metadata=user_meta)
            
            # Note: Brain.chat will now use ctx["processed"] if available
            final_state = await self.brain.chat(processed.clean_text, chat_id, ctx)
            
            # --- NGO FIX: Handle silent offloading (None return) ---
            if final_state is None:
                return None
                
            response = final_state.get("response")
            
            # Track mood/energy for dashboard
            self._last_mood = final_state.get("mood", self._last_mood)
            self._last_energy = final_state.get("energy_level", self._last_energy)
            
            # NONE classification: Brain decided this message is not for us — stay silent
            if response is None:
                return None

            # --- NGO FIX: Record Assistant Response (End of cycle) ---
            # This triggers neural distillation of the interaction
            resp_text = response if isinstance(response, str) else response.get("text", "")
            if resp_text:
                await self.memory.record_chat_message(chat_id, "assistant", resp_text, episode_id=episode_id)
            
            # Standardize response to dict structure
            # Include rich metadata from final_state for GUI/Dashboard
            rich_result = {
                "thoughts": final_state.get("thoughts", []),
                "plan": final_state.get("plan", []),
                "tools_used": final_state.get("tools_used", []),
                "logic": final_state.get("logic", ""),
                "status": final_state.get("status"),
                "approval_id": final_state.get("approval_id"),
                "episode_id": episode_id
            }

            if isinstance(response, str):
                rich_result.update({"text": response, "type": "text"})
            elif isinstance(response, dict):
                rich_result.update(response)
                if "text" not in rich_result and "response" in rich_result:
                    rich_result["text"] = rich_result["response"]
            else:
                rich_result.update({"text": str(response), "type": "text"})
                
            return rich_result
                
        except Exception as e:
            logger.error(f"[AGENT] Chat error: {e}")
            return {"text": "I encountered a problem while processing your request.", "error": str(e)}
        finally:
            from utils.file_handler import cleanup_temp_file
            if context and context.get("file_path"):
                cleanup_temp_file(context["file_path"], source="AGENT_CHAT")

    async def chat_stream(self, message: Union[str, ProcessedInput], chat_id: str, context: Optional[dict] = None) -> Any:
        """
        Async generator that streams chat events in real-time.
        Yields JSON-serializable dictionaries representing events from the graph.
        """
        import json
        
        # 1. Handle Input Type (Preserve Metadata)
        if isinstance(message, str):
            processed = await self.input_pipeline.process(
                message, 
                source=context.get("channel", "telegram") if context else "telegram",
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
            "processed": processed 
        }
        
        if context:
            ctx.update(context)
            
        episode_id = ctx.get("episode_id") or f"ep_{int(datetime.utcnow().timestamp())}"
        ctx["episode_id"] = episode_id 
        
        # We yield a starting event
        yield {"type": "start", "message": "Starting processing...", "episode_id": episode_id}

        try:
            # 3. Record User Message with potential multimedia metadata
            user_meta = {}
            if context:
                if context.get("image_base64"): user_meta["image_base64"] = context.get("image_base64")
                if context.get("audio_base64"): user_meta["audio_base64"] = context.get("audio_base64")
                if context.get("audio_transcript"): user_meta["audio_transcript"] = context.get("audio_transcript")
                if context.get("file_path"): user_meta["file_path"] = context.get("file_path")
                if context.get("mime_type"): user_meta["mime_type"] = context.get("mime_type")
            
            await self.memory.record_chat_message(chat_id, "user", processed.clean_text, episode_id=episode_id, metadata=user_meta)

            initial_state = {
                "chat_id": chat_id,
                "user_message": processed.clean_text,
                "chat_history": [],
                "context": ctx,
                "query_vector": None, # Will be computed in node
                "thoughts": [],
                "response": "",
                "active_task": None,
                "action_result": None,
                "phase": "start",
                "needs_planning": False,
                "plan": [],
                "current_step": 0,
                "task_outputs": [],
                "logic": "",
                "associative_context": "",
                "cycle_complete": False,
                "is_fast_track": False,
                "processed": processed,
                "reply_to": ctx.get("reply_to"),
                "confidence": 0.0,
                "mood": "OPTIMISTIC",
                "energy_level": 1.0,
                "user_affinity": 0.5,
                "error": None,
                "final_decision": None,
                "initial_decision": None,
                "decision_history": [],
                "escalation_level": 0,
                "episode_id": episode_id,
                "replan_context": None,
                "retry_count": 0,
                "planning_thought": None,
                "response_vector": None,
                "speculative_data_context": None,
                "selected_capabilities": None
            }
            
            # Pre-compute embedding
            from utils.embeddings import get_embedding_engine
            engine = get_embedding_engine()
            initial_state["query_vector"] = await engine.get_embedding(processed.clean_text)

            final_state = initial_state
            
            # Track previously emitted thoughts to only send new ones
            last_thought_count = 0
            
            async for event in self.brain.compiled_chat_graph.astream(initial_state):
                for node_name, state_update in event.items():
                    final_state.update(state_update)
                    
                    # Whenever state is updated, check if we have new thoughts
                    current_thoughts = final_state.get("thoughts", [])
                    if len(current_thoughts) > last_thought_count:
                        new_thoughts = current_thoughts[last_thought_count:]
                        for t in new_thoughts:
                            yield {"type": "thought", "content": str(t), "node": node_name}
                        last_thought_count = len(current_thoughts)
                    
                    # Yield specific node events
                    if node_name == "plan" and final_state.get("plan"):
                        yield {"type": "plan", "plan": final_state.get("plan")}
                    
                    elif node_name == "act":
                        step = final_state.get("current_step", 0)
                        total = len(final_state.get("plan", []))
                        yield {"type": "tool_start", "step": step, "total": total, "task": final_state.get("active_task")}
                        
                    elif node_name == "collect":
                        output = final_state.get("task_outputs", [])[-1] if final_state.get("task_outputs") else None
                        yield {"type": "tool_end", "output": output}
                        
                    elif node_name == "generate":
                        yield {"type": "generating_response"}

            response = final_state.get("response")
            
            self._last_mood = final_state.get("mood", self._last_mood)
            self._last_energy = final_state.get("energy_level", self._last_energy)

            resp_text = response if isinstance(response, str) else response.get("text", "") if response else ""
            
            # Prepare rich result with converted objects for storage/stream
            def convert_objs(obj):
                from uuid import UUID
                if isinstance(obj, list): return [convert_objs(x) for x in obj]
                if isinstance(obj, dict): return {k: convert_objs(v) for k, v in obj.items()}
                if isinstance(obj, UUID): return str(obj)
                if hasattr(obj, "model_dump"): return obj.model_dump()
                if hasattr(obj, "dict"): return obj.dict()
                return obj

            rich_result = {
                "thoughts": final_state.get("thoughts", []),
                "plan": convert_objs(final_state.get("plan", [])),
                "tools_used": final_state.get("tools_used", []),
                "logic": final_state.get("logic", ""),
                "status": final_state.get("status"),
                "approval_id": final_state.get("approval_id"),
                "episode_id": episode_id,
                "task_outputs": convert_objs(final_state.get("task_outputs", []))
            }

            if isinstance(response, str):
                rich_result.update({"text": response, "type": "text"})
            elif isinstance(response, dict):
                rich_result.update(response)
                if "text" not in rich_result and "response" in rich_result:
                    rich_result["text"] = rich_result["response"]
            else:
                rich_result.update({"text": str(response) if response else "", "type": "text"})

            # 6. Final Recording (now with ALL response data)
            if resp_text:
                await self.memory.record_chat_message(chat_id, "assistant", resp_text, episode_id=episode_id, metadata=rich_result)

            yield {"type": "final_response", "data": rich_result}

        except Exception as e:
            import traceback
            traceback.print_exc()
            yield {"type": "error", "message": f"I encountered a problem while processing your request: {e}"}
        finally:
            from utils.file_handler import cleanup_temp_file
            if context and context.get("file_path"):
                cleanup_temp_file(context["file_path"], source="AGENT_STREAM")

    async def shutdown(self):
        """Graceful shutdown of all agent components"""
        self._running = False
        logger.info("Shutting down Brain Agent...")
        
        # 1. Stop Queue (prevent new tasks)
        await self.queue.stop()
        
        # 2. Shutdown Brain (closes MCP sessions, etc.)
        await self.brain.shutdown()
        
        # 3. Stop Universal Config Watcher
        if self._universal_config_observer:
            self._universal_config_observer.stop()
            self._universal_config_observer.join()
            logger.info("[AGENT] Universal config watcher stopped.")
        
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
