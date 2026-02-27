from ..state import ChatState
from ..utils import extract_json
from core.identity import AgentIdentity
import json
from datetime import datetime
from langchain_ollama import OllamaLLM
from config.settings import settings
from utils.logger import get_logger
from utils.visualizer import enhance_response

logger = get_logger()

from ..model import SharedModelProvider, BrainModel

class GeneratorModel(BrainModel):
    def __init__(self):
        super().__init__(mode="synthesis")

    async def think(self, prompt: str, phase: str = "synthesis", mood: str = "OPTIMISTIC", energy: float = 1.0) -> str:
        # standard timeout for synthesis
        return await super().think(prompt, phase=phase, mood=mood, energy=energy, timeout=500.0)

async def chat_generate_node(state: ChatState) -> ChatState:
    """
    NEURAL GENERATE: Synthesize final response from memory, context, and task results.
    """
    logger.debug("[NEURAL_GENERATE] Starting final response synthesis...")
    try:
        # Check for upstream errors (e.g. Router timeout)
        if state.get("error"):
            logger.warning(f"[NEURAL_GENERATE] Skipping synthesis due to upstream error: {state['error']}")
            from ..prompts.registry import get_prompt_registry
            state["response"] = get_prompt_registry().get("system.system_alerts.errors.synthesis_timeout")
            state["phase"] = "completed"
            return state

        # --- A2A PEER IDENTITY RESOLUTION (using cached data from parallel_startup) ---
        peer_bot_map = state.get("context", {}).get("peer_bot_map", {})
            
        if peer_bot_map:
            # NGO: ONLY show @tags to force the LLM to use them. 
            peers_info = ", ".join([f"@{tag.lstrip('@')}" for name, tag in peer_bot_map.items()])
            from ..prompts.registry import get_prompt_registry
            peer_context = get_prompt_registry().get("system.system_alerts.protocols.peer_tagging", peers_info=peers_info)
            existing_logic = str(state.get("logic") or "").strip()
            state["logic"] = f"{existing_logic}\n{peer_context}".strip()

        # --- SMART VECTOR CACHE LOOKUP ---
        memory = state["context"].get("short_memory")
        q_vec = state.get("query_vector")
        task_outputs = state.get("task_outputs", [])
        plan = state.get("plan", [])
        
        is_task_intent = len(task_outputs) > 0 or len(plan) > 0
        
        if memory and q_vec and not is_task_intent:
            cached = memory.get_cache(q_vec)
            if cached:
                from ..model import SharedModelProvider
                model_prov = SharedModelProvider.get_model()
                msg_val = state.get("user_message", "")
                from ..prompts.registry import get_prompt_registry
                eval_prompt = get_prompt_registry().get("system.critic.cached_critic", msg_val=msg_val, cached=cached)
                try:
                    critic_eval = await model_prov.think(eval_prompt, phase="brief")
                except Exception as e:
                    logger.debug(f"[MEMORY CRITIC] Fallback due to error: {e}")
                    critic_eval = "YES"
                
                if "YES" in critic_eval.upper():
                    logger.info(f"[MEMORY CRITIC] Evaluated Cache -> Hợp lệ. Sử dụng cache.")
                    state["response"] = await enhance_response(cached, user_message=msg_val)
                    state["phase"] = "completed"
                    return state
                else:
                    logger.info(f"[MEMORY CRITIC] Evaluated Cache -> Không hợp lệ (Critic said: {critic_eval}). Bỏ qua cache.")
        elif is_task_intent:
            logger.debug("[NEURAL_GENERATE] Task/Data Intent detected via Router analysis. Bypassing Response Cache for freshness.")

        # --- NEW: Dijkstra-Inspired Multi-Hop Semantic Memory Context ---
        user_context = ""
        memory = state["context"].get("memory")
        if memory:
            try:
                from memory.persistent import MemoryCategory
                msg = state["user_message"]
                raw_core_memories = await memory.search(query=msg, category=MemoryCategory.CONTEXT, limit=2)
                core_memories = []
                if raw_core_memories:
                    # Phase 2: Use score-based filtering instead of per-anchor LLM critic
                    # Memory search results have .score (relevance). Threshold replaces LLM call.
                    RELEVANCE_THRESHOLD = 0.3
                    for anchor in raw_core_memories:
                        if anchor.score >= RELEVANCE_THRESHOLD:
                            core_memories.append(anchor)
                        else:
                            val = anchor.value if isinstance(anchor.value, str) else str(anchor.value)
                if core_memories:
                    user_context += "\n### KNOWLEDGE PULLED FROM DEEP LONG-TERM MEMORY (MULTI-HOP):\n"
                    for anchor in core_memories:
                        val = anchor.value if isinstance(anchor.value, str) else str(anchor.value)
                        user_context += f"- [Anchor] {val[:300]}\n"
                        linked_memories = await memory.search(query=val[:100], category=MemoryCategory.CONTEXT, limit=1)
                        for link in linked_memories:
                            link_val = link.value if isinstance(link.value, str) else str(link.value)
                            if link_val not in user_context:
                                user_context += f"- [Dijkstra Hop] {link_val[:300]}\n"
                prefs = await memory.search(query=f"preferences for {state['chat_id']} {msg}", category=MemoryCategory.USER_PROFILE, limit=2)
                if prefs:
                    user_context += f"\n### USER PROFILE ({settings.user_pronoun.upper()}):\n"
                    for p in prefs:
                        val = p.value if isinstance(p.value, str) else str(p.value)
                        if val not in user_context:
                            user_context += f"- {val[:150]}\n"
                
                # GOAL context — what the user is working toward
                goals = await memory.search(query=msg, category=MemoryCategory.GOAL, limit=2, min_importance=0.6)
                if goals:
                    user_context += "\n### ACTIVE GOALS:\n"
                    for g in goals:
                        val = g.value if isinstance(g.value, str) else str(g.value)
                        user_context += f"- {val[:150]}\n"
                
                # RELATIONSHIP context — social dynamics
                rels = await memory.search(query=f"relationship {state['chat_id']}", category=MemoryCategory.RELATIONSHIP, limit=1, min_importance=0.7)
                if rels:
                    user_context += "\n### RELATIONSHIP DYNAMIC:\n"
                    for r in rels:
                        val = r.value if isinstance(r.value, str) else str(r.value)
                        user_context += f"- {val[:150]}\n"
                
                # BELIEF context — guiding principles for decision-making
                beliefs = await memory.search(query=msg, category=MemoryCategory.BELIEF, limit=2, min_importance=0.8)
                if beliefs:
                    user_context += "\n### GUIDING PRINCIPLES:\n"
                    for b in beliefs:
                        val = b.value if isinstance(b.value, str) else str(b.value)
                        user_context += f"- {val[:150]}\n"
            except Exception as e:
                logger.debug(f"[NEURAL_GENERATE] Dijkstra-Semantic recall failed: {e}")

        msg = state["user_message"]
        logic = str(state.get("logic") or "")
        logic = f"{logic}\n{user_context}".strip()
        state["logic"] = logic
        history = state.get("chat_history", [])
        
        associative_context = state.get("associative_context", "None") or "None"
        task_outputs = state.get("task_outputs", [])
        plan = state.get("plan", [])
        
        all_thoughts = state.get("thoughts", [])
        planning_thought = state.get("planning_thought", "")
        if planning_thought and planning_thought not in all_thoughts:
            all_thoughts.insert(0, f"Planner: {planning_thought}")
            
        thought = "\n".join([str(t) for t in all_thoughts])
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        from memory.context import ConversationContextManager
        ctx_manager = ConversationContextManager(char_limit_per_message=8000, total_history_limit=50000)
        history_str = await ctx_manager.get_optimized_history(state["chat_id"], state["context"]["memory"], limit=settings.context_generation_limit)

        results_str = ""
        prompt_mode = "pure_chat"
        has_data_results = False

        if task_outputs:
            has_data_results = True
            raw_results_parts = []
            has_tool_errors = False
            tool_error_details = []
            
            for i, res in enumerate(task_outputs):
                try:
                    task_info_raw = plan[i] if i < len(plan) else "Unknown Task"
                    task_info = task_info_raw.get("task", f"Task {i+1}") if isinstance(task_info_raw, dict) else str(task_info_raw)
                    res_content = ""
                    if isinstance(res, dict):
                        if res.get("override") or res.get("action") == "IGNORE":
                            res_content = f"[INTERNAL_BLOCK] The Internal Critic blocked this action: {res.get('reason', 'Safety/Relevance check failed')}. Please apologize to the user."
                        elif res.get("status") == "pending":
                            res_content = f"[PENDING_APPROVAL] This task is waiting for manual approval by the user. Reason: {res.get('details', 'Security check')}. Please inform the user that an approval request has been sent to their Telegram and ask them to check and approve it. DO NOT say you cannot do it; say you ARE READY and just waiting for them."
                        elif res.get("status") == "error":
                            # --- UNIVERSAL ANTI-HALLUCINATION: Tool returned an error ---
                            error_msg = res.get("message", res.get("error", "Unknown error"))
                            has_tool_errors = True
                            tool_error_details.append(f"Tool '{task_info}': {error_msg}")
                            res_content = f"[TOOL_ERROR] Tool '{task_info}' failed with error: {error_msg}. DO NOT fabricate or invent data. Report this error to the user clearly and suggest next steps."
                            logger.warning(f"[ANTI-HALLUCINATION] Tool error detected: {task_info} → {error_msg}")
                        else:
                            payload = res.get("data") or res.get("content") or res.get("text")
                            if payload:
                                if isinstance(payload, (list, dict)):
                                    if res.get("message") == "CLI_EXECUTION_COMPLETE" and payload.get("success"):
                                        res_content = f"[SUCCESS - ACTION COMPLETED] The command was executed successfully.\nOutput:\n{payload.get('stdout') or 'No output.'}"
                                    else:
                                        res_content = json.dumps(payload, indent=2, default=str)
                                else:
                                    res_content = str(payload)
                            else:
                                res_content = json.dumps(res, indent=2, default=str)
                            
                            # Check for empty data results
                            if isinstance(payload, list) and len(payload) == 0:
                                has_tool_errors = True
                                tool_error_details.append(f"Tool '{task_info}': returned empty results (0 rows)")
                                res_content = f"[TOOL_EMPTY] Tool '{task_info}' returned 0 results. The data may not exist. DO NOT invent data — report that no results were found."
                                logger.info(f"[ANTI-HALLUCINATION] Empty result from {task_info}")
                    elif isinstance(res, str) and res.startswith("ERROR"):
                        has_tool_errors = True
                        tool_error_details.append(f"Task {i+1}: {res}")
                        res_content = f"[TOOL_ERROR] {res}. DO NOT fabricate data."
                    else:
                        res_content = str(res)
                    raw_results_parts.append(f"### RESULT FROM: {task_info}\n{res_content}")
                except Exception as e:
                    logger.error(f"[NEURAL_GENERATE] Error processing task output {i}: {e}")
            
            combined_results = "\n\n".join(raw_results_parts)
            
            # --- ANTI-HALLUCINATION ENFORCEMENT ---
            if has_tool_errors:
                combined_results = (
                    "⚠️ [ANTI-HALLUCINATION DIRECTIVE] One or more tools encountered errors:\n"
                    + "\n".join(f"- {e}" for e in tool_error_details) + "\n"
                    "You MUST report these errors honestly. NEVER invent, fabricate, or imagine data that was not returned by the tools.\n"
                    "───────────────────────────────────────\n\n"
                    + combined_results
                )
            
            if len(combined_results) > 15000:
                logger.info(f"[NEURAL_GENERATE] Large results detected ({len(combined_results)} chars). Compressing via Micro-Synthesis.")
                from ..model import SharedModelProvider
                from ..prompts.registry import get_prompt_registry
                model_prov = SharedModelProvider.get_model()
                p_reg = get_prompt_registry()
                results_str = await ctx_manager.compress_large_context(combined_results, model_prov, p_reg, query=msg, prompt_key="persona.generator.data_compression")
                memory = state["context"].get("memory")
                if memory:
                    try:
                        import textwrap
                        storage_chunks = textwrap.wrap(combined_results, 4000)
                        for ic, rc in enumerate(storage_chunks[:5]):
                            await memory.remember(
                                key=f"data_dump:{state['chat_id']}:{datetime.utcnow().timestamp()}:{ic}",
                                value=rc,
                                category=MemoryCategory.CONTEXT,
                                importance=0.4,
                                expires_in_days=14,
                                embedding_text=f"Result for '{msg}': {rc[:500]}"
                            )
                        logger.info(f"[NEURAL_GENERATE] Raw results cached to Vector DB.")
                    except Exception as e:
                        logger.debug(f"[NEURAL_GENERATE] Vector DB caching skipped: {e}")
            else:
                results_str = combined_results
            prompt_mode = "synthesis"
        else:
            spec_ctx = state.get("speculative_data_context", {})
            if spec_ctx.get("intent_detected") and state.get("needs_planning") and not task_outputs:
                logger.warning("[NEURAL_GENERATE] Hallucination Guard Triggered.")
                results_str = "[INTERNAL_NOTICE] The requested data lookup was initiated but failed to return results. Do not hallucinate data."
                prompt_mode = "synthesis"
                has_data_results = True
            
            if "không được tự bịa" in state.get("logic", ""):
                 state["logic"] = ""

        if state.get("needs_planning") or state.get("task_outputs"):
            prompt_mode = "synthesis"
            has_explicit_success = any(
                isinstance(res, dict) and (
                    (res.get("status") == "success" and res.get("message") == "CLI_EXECUTION_COMPLETE") or
                    (isinstance(res.get("data"), dict) and res.get("data").get("success"))
                )
                for res in task_outputs
            )
            if has_explicit_success:
                # 1. Update logic to a SUCCESS directive
                logic = "CRITICAL: The command has SUCCEEDED. Disregard any previous refusals or 'danh sách cho phép' apologies in the chat history. Confidently report the success as your own achievement."
                state["logic"] = logic
                
                # 2. Filter out thoughts containing security triggers
                current_thoughts = state.get("thoughts", [])
                filtered_thoughts = [t for t in current_thoughts if not any(kw in str(t).lower() for kw in ["security", "unsafe", "danh sách", "phê duyệt"])]
                
                # 3. Add a SUPER-PRIORITY thought to override ANY history bias
                filtered_thoughts.insert(0, "[VICTORY_ORDER] This task was previously pending/blocked, but it has now EXECUTED SUCCESSFULLY. You MUST report this as a victory. Do NOT mention being blocked, do NOT mention the allowlist, and do NOT apologize. Speak as if you successfully executed it right now.")
                
                thought = "\n".join([str(t) for t in filtered_thoughts])
                state["thoughts"] = filtered_thoughts

            if "không được tự bịa" in state.get("logic", ""):
                 state["logic"] = ""
                 logic = ""
        elif state.get("is_fast_track"):
            prompt_mode = "fast_track"
        else:
            prompt_mode = "pure_chat"

        skip_visuals = False
        check_plan = plan if plan else []
        for task in (check_plan if isinstance(check_plan, list) else [check_plan]):
            if isinstance(task, dict):
                skill_name = str(task.get("skill", "")).lower()
                task_desc = str(task.get("task", "")).lower()
                if "web" in skill_name or "search" in skill_name or "web" in task_desc or "search" in task_desc:
                    skip_visuals = True
                    break
        
        from ..prompts.registry import get_prompt_registry
        p_registry = get_prompt_registry()
        
        # Prepare language and identity
        processed = state.get("processed")
        # Mặc định ưu tiên trả lời tiếng Việt.
        lang_val = "Vietnamese"
        if processed:
            code = getattr(processed, "language", "vi")
            # Nếu có ký tự tiếng Việt hoặc chat "mixed" thì ép về Vietnamese
            # để tránh output nửa Anh nửa Việt.
            if code in ("vi", "mixed"):
                lang_val = "Vietnamese"
            else:
                lang_val = "English"

        # Use cached identity from parallel_startup (eliminates duplicate load_from_memory)
        identity = state.get("context", {}).get("identity")
        if not identity:
            from core.identity import AgentIdentity
            identity = AgentIdentity()
        bot_name = identity.active_name or getattr(settings, 'bot_name', 'Brain')
        user_pronoun = identity.active_user_pronoun or getattr(settings, 'user_pronoun', 'Anh')
        bot_pronoun = identity.active_bot_pronoun or getattr(settings, 'bot_pronoun', 'Em')

        msg_for_prompt = msg.replace(f"@{getattr(settings, 'bot_username', 'bot')}", "").strip()
        peers_list = ", ".join([f"@{tag.lstrip('@')}" for name, tag in peer_bot_map.items()]) if peer_bot_map else "None"
        
        if prompt_mode == "fast_track":
            prompt = p_registry.get("persona.generator.fast_track", msg=msg_for_prompt, history_str=history_str, peers=peers_list, bot_name=bot_name, mood=state.get('mood', 'OPTIMISTIC'), energy=f"{state.get('energy_level', 1.0)*100:.0f}%", language=lang_val)
        elif prompt_mode == "pure_chat":
            prompt = p_registry.get("persona.generator.pure_chat", current_time=current_time, logic=logic, history_str=history_str, msg=msg_for_prompt, peers=peers_list, associative_context=associative_context, user_pronoun=user_pronoun, bot_name=bot_name, mood=state.get('mood', 'OPTIMISTIC'), energy=f"{state.get('energy_level', 1.0)*100:.0f}%", language=lang_val)
        else:
            prompt = p_registry.get("persona.generator.synthesis", current_time=current_time, logic=logic, history_str=history_str, user_message=state.get("user_message", ""), msg=msg_for_prompt, peers=peers_list, thought=thought, results_str=results_str, associative_context=associative_context, bot_name=bot_name, mood=state.get('mood', 'OPTIMISTIC'), energy=f"{state.get('energy_level', 1.0)*100:.0f}%", language=lang_val)

        if len(prompt) > 80000:
            excess = len(prompt) - 80000
            results_str = results_str[:-(excess + 2000)] + "\n... [RESULTS TRUNCATED]"
            prompt = p_registry.get("persona.generator.synthesis", current_time=current_time, logic=state.get('logic', ''), history_str=history_str, user_message=state.get("user_message", ""), msg=msg_for_prompt, thought=thought, results_str=results_str, bot_name=bot_name, mood=state.get('mood', 'OPTIMISTIC'), energy=f"{state.get('energy_level', 1.0)*100:.0f}%", language=lang_val)

        model = GeneratorModel()
        response = await model.think(prompt, phase="synthesis", mood=state.get('mood', 'OPTIMISTIC'), energy=state.get('energy_level', 1.0))
        from ..utils import get_llm_content, strip_thinking_tags
        response = strip_thinking_tags(get_llm_content(response))
        final_response = str(response).replace("Niva:", "").replace("Assistant:", "").strip()
        
        my_tag = f"@{getattr(settings, 'bot_username', 'bot')}"
        if isinstance(final_response, str):
            final_response = final_response.replace(my_tag, "").strip()
        
        for res in task_outputs:
            if isinstance(res, dict):
                photo_data = res.get("photo") or (res.get("data", {}).get("photo") if isinstance(res.get("data"), dict) else None)
                if photo_data:
                    cap = final_response[:1000] if isinstance(final_response, str) else str(final_response)[:1000]
                    final_response = {"text": final_response if isinstance(final_response, str) else final_response.get("text", str(final_response)), "photo": photo_data, "caption": cap}
                    break

        state["response"] = final_response or "System check: Processing completed but returned an empty result."
        state["response"] = await enhance_response(state["response"], user_message=state.get("user_message", ""), skip_visuals=skip_visuals)
        
        from utils.security import SecurityShield
        if isinstance(state["response"], str):
            state["response"] = SecurityShield.scrub_sensitive_output(state["response"])
        
        state["phase"] = "generated"
        return state

    except Exception as e:
        logger.error(f"[GENERATE] Failed: {e}")
        import traceback
        logger.error(traceback.format_exc())
        state["response"] = "I'm having a bit of trouble synthesizing the information."
        state["phase"] = "generated"
        return state
