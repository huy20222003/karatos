import asyncio
import time
from typing import Optional, Any
from langgraph.graph import StateGraph, END

from config.settings import settings
from utils.logger import get_logger
from core.identity import AgentIdentity

# Imports from modular brain
from core.brain.state import AgentState, ChatState
from core.brain.utils import route_chat, should_continue_execution, should_investigate, should_continue
from utils.file_handler import cleanup_temp_file
from channels.telegram.channel import get_telegram_channel
from core.brain.nodes.observe import chat_observe_node, observe_node
from core.brain.nodes.router import chat_route_node
from core.brain.nodes.plan import chat_plan_node, chat_prepare_step_node
from core.brain.nodes.act import chat_act_node, chat_collect_result_node
from core.brain.nodes.generate import chat_generate_node
from core.brain.nodes.post_generate import chat_post_generate_node
from core.brain.nodes.escalation import chat_escalation_node
from core.brain.nodes.autonomous import reason_node, investigate_node, decide_node, act_node, reflect_node as auto_reflect_node
from core.brain.nodes.critic import critic_node
from core.brain.nodes.context_critic import context_critic_node
from core.brain.nodes.goal_proposer import propose_goals_node
from core.brain.nodes.result_critic import result_critic_node

logger = get_logger()

class Brain:
    """
    Main Brain Class
    Orchestrates the thinking process using LangGraph.
    """
    def __init__(self):
        self.compiled_chat_graph = None
        self.compiled_graph = None
        self.graph = None
        self.is_initialized = False
        self.model = None

    async def initialize(self) -> bool:
        """Initialize the brain and compile the graph"""
        logger.debug("[BRAIN] Starting initialize()...")
        try:
            # Initialize the Brain's model using the configured provider.
            # IMPORTANT: Do not hardcode Ollama here; SharedModelProvider handles provider selection.
            logger.debug("[BRAIN] Getting SharedModelProvider model...")
            from core.brain.model import SharedModelProvider
            self.model = SharedModelProvider.get_model()
            
            # Warmup is now handled by BrainAgent to prevent duplication.
            logger.info("Brain connection established")
            
            # Build Graphs
            logger.debug("[BRAIN] Building autonomous graph...")
            self._build_graph()
            logger.debug("[BRAIN] Building chat graph...")
            self._build_chat_graph()
            
            self.is_initialized = True
            logger.info("Brain initialized with Modular LangGraph Architecture")
            logger.debug("[BRAIN] initialize() complete.")
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize Brain: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False

    def _build_graph(self):
        """Compile the autonomous agent graph"""
        self.graph = StateGraph(AgentState)
        self.graph.add_node("observe", observe_node)
        self.graph.add_node("reason", reason_node)
        self.graph.add_node("investigate", investigate_node)
        self.graph.add_node("decide", decide_node)
        self.graph.add_node("critic", critic_node)
        self.graph.add_node("act", act_node)
        self.graph.add_node("reflect", auto_reflect_node)
        self.graph.add_node("propose_goals", propose_goals_node)
        
        self.graph.set_entry_point("observe")
        self.graph.add_edge("observe", "reason")
        
        self.graph.add_conditional_edges(
            "reason", 
            should_investigate, 
            {"investigate": "investigate", "decide": "decide"}
        )
        
        self.graph.add_edge("investigate", "decide")
        self.graph.add_edge("decide", "critic") # Skipped evolve node
        # self.graph.add_edge("decide", "evolve")
        # self.graph.add_edge("evolve", "critic")
        self.graph.add_edge("critic", "act")
        self.graph.add_edge("act", "reflect")
        self.graph.add_edge("reflect", "propose_goals")
        self.graph.add_edge("propose_goals", END)
        
        self.compiled_graph = self.graph.compile()
        logger.debug("Modular Autonomous Graph compiled successfully")

    async def run_cycle(self, audit_logs: list[dict], context: dict = None) -> dict:
        """Entry point for the Autonomous Loop"""
        if not self.is_initialized:
             logger.error("Brain not initialized. Call initialize() first.")
             return {"error": "Brain not initialized"}
             
        initial_state: AgentState = {
            "phase": "start",
            "audit_logs": audit_logs,
            "context": context or {},
            "anomalies": [],
            "current_target": None,
            "evidence": [],
            "thoughts": [],
            "analysis": None,
            "active_task": None,
            "action_result": None,
            "should_investigate": False,
            "investigation_complete": False,
            "cycle_complete": False,
            "mood": "OPTIMISTIC",
            "energy_level": 1.0,
            # Baseline motivational profile; values will be evolved in reflect_node.
            "drives": {
                "safety": 0.9,
                "curiosity": 0.4,
                "connection": 0.3,
                "mastery": 0.6,
            },
            "goals": [],
            "error": None,
            "replan_context": None,
            "retry_count": 0
        }
        logger.info("Starting Modular LangGraph thinking cycle...")
        try:
            final_state = await self.compiled_graph.ainvoke(initial_state)
            logger.info(f"Cycle complete. Thoughts generated: {len(final_state.get('thoughts', []))}")
            return final_state
        except Exception as e:
            logger.error(f"[BRAIN] Autonomous Cycle Failed: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return {"error": str(e)}
            
    def get_stats(self) -> dict:
        """Get brain status statistics"""
        return {
            "initialized": self.is_initialized,
            "model_loaded": self.model is not None,
            "graph_compiled": self.compiled_graph is not None,
            "chat_graph_compiled": self.compiled_chat_graph is not None,
            "ollama_model": settings.ollama_model_name
        }

    def _build_chat_graph(self):
        """Compile the chat reasoning graph"""
        graph = StateGraph(ChatState)
        
        # Add Nodes (Phase 2: scanner merged into planner — removed as separate node)
        graph.add_node("parallel_startup", chat_parallel_startup_node)
        graph.add_node("route", chat_route_node)
        graph.add_node("plan", chat_plan_node)
        graph.add_node("prepare_step", chat_prepare_step_node)
        graph.add_node("act", chat_act_node)
        graph.add_node("result_critic", result_critic_node)
        graph.add_node("collect", chat_collect_result_node)
        graph.add_node("generate", chat_generate_node)
        graph.add_node("escalation", chat_escalation_node)
        graph.add_node("post_generate", chat_post_generate_node) 
        graph.add_node("critic", critic_node) # Safety Guard
        graph.add_node("context_critic", context_critic_node)
        
        # Define Edges
        graph.set_entry_point("parallel_startup")
        graph.add_edge("parallel_startup", "route")
        
        # Routing Logic — plan goes directly to planner (scanner merged in)
        graph.add_conditional_edges(
            "route",
            route_chat,
            {
                "plan": "plan",                         # Direct to planner
                "generate": "context_critic",           # Audit context before generate
                "prepare_step": "prepare_step",
                "__end__": END
            }
        )
        
        graph.add_edge("context_critic", "generate")
        
        graph.add_edge("plan", "prepare_step")
        
        # --- CRITIC INTEGRATION (CHAT SAFETY) ---
        # "Prepare Step" -> "Critic" -> "Act"
        # The Critic reviews the prepared decision before execution.
        graph.add_edge("prepare_step", "critic")
        graph.add_edge("critic", "act")
        
        graph.add_edge("act", "result_critic")
        graph.add_edge("result_critic", "collect")
        
        # Loop Logic
        graph.add_conditional_edges(
            "collect", 
            should_continue_execution, 
            {
                "prepare_step": "prepare_step", 
                "generate": "generate",
                "plan": "plan"
            }
        )
        
        # Brain 2.6: Escalation Loop (CHAT -> PLAN if needed)
        from core.brain.utils import should_escalate_chat
        graph.add_edge("generate", "escalation")
        graph.add_conditional_edges(
            "escalation",
            should_escalate_chat,
            {
                "plan": "plan",
                "post_generate": "post_generate"
            }
        )
        graph.add_edge("post_generate", END)
        
        self.compiled_chat_graph = graph.compile()
        logger.debug("Optimized Chat Graph compiled successfully")

    async def chat(self, user_message: str, chat_id: str, context: dict = None) -> dict:
        """Main entry point for chat interaction"""
        if not self.is_initialized:
            return {"response": "My reasoning engine is currently offline."}

        # --- OPTIMIZATION: PRE-COMPUTE EMBEDDING ---
        from utils.embeddings import get_embedding_engine
        engine = get_embedding_engine()
        query_vector = await engine.get_embedding(user_message)
        # -------------------------------------------

        if context is None: context = {}
        initial_state: ChatState = {
            "chat_id": chat_id,
            "user_message": user_message,
            "chat_history": [],
            "context": context,
            "query_vector": query_vector, 
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
            "processed": context.get("processed"), # Preserved metadata
            "reply_to": context.get("reply_to"),   # Phase 32: Original Message ID
            "confidence": 0.0,
            "mood": "OPTIMISTIC",

            "energy_level": 1.0,
            "user_affinity": 0.5,
            "error": None,
            "final_decision": None,
            "decision_history": [],
            "escalation_level": 0,
            "episode_id": context.get("episode_id") or f"ep_{int(time.time())}",
            "replan_context": None,
            "retry_count": 0
        }
        initial_state["response_vector"] = None 
        
        t_start = time.time()
        logger.info(f"Starting Modular Chat Graph cycle for {chat_id}...")
        
        try:
            # Execution Strategy:
            # 1. Run until 'route' or 'plan' node
            # 2. If it's a PLAN (and not fast track), Notify User and continue in background
            # 3. Else, return final state immediately
            
            final_state = initial_state
            is_plan_offloaded = False
            
            async for event in self.compiled_chat_graph.astream(initial_state):
                for node_name, state_update in event.items():
                    final_state.update(state_update)
                    
                    # Detect if we need to offload
                    # NGO: Added check for 'is_test' to allow synchronous testing
                    if node_name == "plan" and final_state.get("plan") and not final_state.get("is_fast_track") and not final_state.get("context", {}).get("is_test"):
                        logger.info(f"[BRAIN] Offloading complex plan execution for {chat_id}")
                        
                        # --- CHANNEL AGNOSTIC NOTIFICATION ---
                        from channels.base import get_channel
                        channel_name = final_state.get("context", {}).get("channel", "telegram")
                        channel = get_channel(channel_name)
                        
                        # --- NGO FIX: CONCISE DYNAMIC ACKNOWLEDGEMENT ---
                        if channel:
                            # Generate a dynamic notification
                            status_msg = await self._generate_status_update(
                                final_state, 
                                event_type="PLAN_ACK", 
                                event_detail="Đã nhận lệnh và đang triển khai!"
                            )
                            await channel.send(status_msg, recipient=chat_id, reply_to=final_state.get("reply_to"))
                        
                        # Launch background monitor for the REST of the graph (Reset Fast-Track for full synthesis)
                        logger.info(f"[BRAIN] Resetting is_fast_track=False for background synthesis on {chat_id}")
                        final_state["is_fast_track"] = False
                        asyncio.create_task(self._monitor_plan_execution(final_state, chat_id))
                            
                        is_plan_offloaded = True
                        break # Break the astream loop for the main thread
                
                if is_plan_offloaded:
                    break

            if is_plan_offloaded:
                return None # True silence for the return value

            t_end = time.time()
            logger.info(f"[PERF] Total Brain Cycle took: {t_end - t_start:.3f}s")
            return final_state
            
        except Exception as e:
            logger.error(f"[BRAIN] Graph execution failed: {e}")
            import traceback
            traceback.print_exc()
            return {"response": "I apologize, an error occurred during processing.", "error": str(e)}

    async def _generate_status_update(self, state: ChatState, event_type: str, event_detail: str) -> str:
        """
        Generate a witty, persona-consistent status update using the LLM.
        """
        try:
            from core.brain.nodes.generate import GeneratorModel
            from core.brain.prompts.registry import get_prompt_registry
            from config.settings import settings
            
            model = GeneratorModel()
            p_registry = get_prompt_registry()
            
            bot_name = getattr(settings, 'bot_name', 'Brain')
            total_steps = len(state.get("plan", []))
            current_step = state.get("current_step", 0) + 1
            
            # Determine target language (not limited to vi/en)
            from utils.language import language_for_prompt, normalize_language_code
            processed = state.get("processed")
            code = getattr(processed, "language", None) if processed else None
            if not code:
                code = getattr(settings, "user_language", None) or "en"
            lang_val = language_for_prompt(normalize_language_code(code, default="en"), default="en")

            prompt = p_registry.get(
                "persona.generator.status_notification",
                bot_name=bot_name,
                mood=state.get("mood", "OPTIMISTIC"),
                energy=f"{state.get('energy_level', 1.0)*100:.0f}%",
                event_type=event_type,
                event_detail=event_detail,
                total_steps=total_steps,
                current_step=current_step,
                language=lang_val
            )
            
            response = await model.think(prompt, phase="status_check")
            
            from core.brain.utils import get_llm_content, strip_thinking_tags, extract_json
            content = strip_thinking_tags(get_llm_content(response))
            
            # --- NGO FIX: Unpack JSON if necessary ---
            json_data = extract_json(content)
            if isinstance(json_data, dict):
                content = json_data.get("message") or json_data.get("text") or content
            
            return str(content).strip() or f"🔄 {event_detail}"
            
        except Exception as e:
            logger.error(f"[BRAIN] Status generation failed: {e}")
            return f"🔄 {event_detail}"

    async def _monitor_plan_execution(self, state: ChatState, chat_id: str):
        """
        Background monitor for plan execution with progress updates.
        """
        from channels.base import get_channel
        channel_name = state.get("context", {}).get("channel", "telegram")
        channel = get_channel(channel_name)
        
        if not channel:
            logger.warning(f"[BRAIN] Channel '{channel_name}' not available. Falling back to 'telegram'.")
            channel_name = "telegram"
            channel = get_channel("telegram")
            
        if not channel:
            logger.error(f"[BRAIN] Critical: No valid channel available for monitoring {chat_id}.")
            return

        try:
            # Re-start astream from where we left off
            async for event in self.compiled_chat_graph.astream(state):
                for node_name, state_update in event.items():
                    state.update(state_update)
                    
                    # 1. Restore status update for 'act' node to provide visibility
                    if node_name == "act":
                        status_msg = await self._generate_status_update(
                            state, 
                            event_type="ACT_PROGRESS", 
                            event_detail=f"Đang thực hiện bước {state.get('current_step', 0) + 1}/{len(state.get('plan', []))}"
                        )
                        # Progress updates should feel like ambient status,
                        # not strict replies to the original user message.
                        await channel.send(status_msg, recipient=chat_id)
                    # 2. Skip synthesis update to reduce noise
                    elif node_name == "generate":
                        pass

            response = state.get("response")
            reply_to = state.get("reply_to")
            if response:
                logger.info(f"[MONITOR] Delivering final response to {chat_id} via {channel_name} (Reply to: {reply_to})")
                await channel.send(response, recipient=chat_id, reply_to=reply_to)
                logger.info(f"[MONITOR] Plan execution complete for {chat_id}")
                
                # --- NGO FIX: A2A Mailbox dropping for Background Tasks ---
                try:
                    resp_text = ""
                    if isinstance(response, str):
                        resp_text = response
                    elif isinstance(response, dict):
                        resp_text = response.get("text") or response.get("caption") or ""
                        
                    if resp_text:
                        import re
                        mentions = set(re.findall(r'@\w+', resp_text))
                        if mentions:
                            from config.settings import settings
                            my_username = getattr(settings, 'bot_username', 'SystemBot')
                            my_username = f"@{my_username}" if not my_username.startswith('@') else my_username
                            
                            from tools.mcp_bridge import get_mcp_bridge
                            bridge = get_mcp_bridge()
                            
                            for m in mentions:
                                if m.lower() != my_username.lower():
                                    peer_name = m.lstrip('@').lower()
                                    await bridge.execute(f"peer:{peer_name}:receive_message", {
                                        "sender": my_username,
                                        "message": resp_text,
                                        "chat_id": str(chat_id)
                                    })
                except Exception as e:
                    logger.error(f"[MONITOR] A2A drop failed in background: {e}")
        except Exception as e:
            logger.error(f"[MONITOR] Background execution failed: {e}")
            await channel.send(f"❌ Niva encountered an issue during execution: {str(e)}", recipient=chat_id)
        finally:
            # NGO: Cleanup temp files after background task completion
            file_path = state.get("context", {}).get("file_path")
            cleanup_temp_file(file_path, source="MONITOR")

    async def shutdown(self):
        """Shutdown brain resources (MCP sessions, etc.)"""
        logger.info("[BRAIN] Shutting down brain resources...")
        try:
            from tools.mcp_bridge import get_mcp_bridge
            mcp = get_mcp_bridge()
            await mcp.shutdown()
            logger.info("[BRAIN] MCP sessions closed.")
        except Exception as e:
             logger.error(f"[BRAIN] Error during shutdown: {e}")

async def chat_parallel_startup_node(state: ChatState) -> ChatState:
    """
    PARALLEL STARTUP (Optimized):
    Run Observation, Data Speculation, and I/O Prefetch in concurrent threads.
    """

    # 1. Observation Task (loads history, does deep_recall, handles vision)
    obs_task = chat_observe_node(state)
    
    # 2. Data Speculation Task (Pre-fetch DB Schema if DB keywords detected)
    from core.brain.nodes.speculator import data_speculator_node
    spec_task = data_speculator_node(state)
    
    # 3. I/O Prefetch Task (peer bots + identity — previously duplicated 3x each)
    async def prefetch_shared_io(st: ChatState):
        result = {}
        
        # Fetch peer bot registrations (was duplicated in router, plan, generate)
        try:
            from tools.mcp_bridge import get_mcp_bridge
            mcp = get_mcp_bridge()
            peer_bot_map = await mcp.get_peer_registry()
            result["_cached_peer_bot_map"] = peer_bot_map or {}
        except Exception as e:
            logger.debug(f"[PREFETCH] Peer bot fetch failed: {e}")
            result["_cached_peer_bot_map"] = {}
        
        # Load identity from memory (was duplicated in router, generate)
        try:
            from core.identity import AgentIdentity
            identity = AgentIdentity()
            memory = st.get("context", {}).get("memory")
            chat_id = st.get("chat_id")
            if memory and chat_id:
                await identity.load_from_memory(memory, chat_id)
            result["_cached_identity"] = identity
        except Exception as e:
            logger.debug(f"[PREFETCH] Identity load failed: {e}")
            result["_cached_identity"] = None
        
        return result

    prefetch_task = prefetch_shared_io(state)
    
    # Execute all 3 in parallel
    results = await asyncio.gather(obs_task, spec_task, prefetch_task)
    
    # Merge results into state
    for res_state in results:
        if isinstance(res_state, dict):
            # For prefetch results, store in context to avoid polluting top-level state
            if "_cached_peer_bot_map" in res_state or "_cached_identity" in res_state:
                ctx = state.get("context", {})
                if "_cached_peer_bot_map" in res_state:
                    ctx["peer_bot_map"] = res_state.pop("_cached_peer_bot_map")
                if "_cached_identity" in res_state:
                    ctx["identity"] = res_state.pop("_cached_identity")
                state["context"] = ctx
            else:
                state.update(res_state)
        
    return state


