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
            state["response"] = get_prompt_registry().get("system_alerts.errors.synthesis_timeout")
            state["phase"] = "completed"
            return state

        # --- A2A PEER IDENTITY RESOLUTION ---
        peer_bot_map = {}
        try:
            from skills.mcp_realm import get_mcp_realm
            mcp = get_mcp_realm()
            peer_bot_map = await mcp.get_bot_registrations()
        except Exception as e:
            logger.debug(f"[NEURAL_GENERATE] Failed to fetch peer registrations: {e}")
            
        if peer_bot_map:
            # NGO: ONLY show @tags to force the LLM to use them. 
            peers_info = ", ".join([f"@{tag.lstrip('@')}" for name, tag in peer_bot_map.items()])
            from ..prompts.registry import get_prompt_registry
            peer_context = get_prompt_registry().get("system_alerts.protocols.peer_tagging", peers_info=peers_info)
            existing_logic = str(state.get("logic") or "").strip()
            state["logic"] = f"{existing_logic}\n{peer_context}".strip()

        # --- SMART VECTOR CACHE LOOKUP (Boss's Request: Freshness & Optimization) ---
        memory = state["context"].get("short_memory")
        q_vec = state.get("query_vector")
        task_outputs = state.get("task_outputs", [])
        plan = state.get("plan", [])
        
        # 1. Freshness Check: Bypass cache if any tasks were planned/executed (Intent-based)
        is_task_intent = len(task_outputs) > 0 or len(plan) > 0
        
        if memory and q_vec and not is_task_intent:
            cached = memory.get_cache(q_vec)
            if cached:
                from ..model import SharedModelProvider
                model_prov = SharedModelProvider.get_model()
                msg_val = state.get("user_message", "")
                
                from ..prompts.registry import get_prompt_registry
                eval_prompt = get_prompt_registry().get("system.cache_critic.prompt", msg_val=msg_val, cached=cached)
                
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
                
                # 1. Initial Prompt-free Semantic Match (Direct Vector Distance)
                # Instead of hardcoded keywords, we always do a fast, lightweight K-NN search.
                # If distance > threshold, there are relevant long-term memories.
                raw_core_memories = await memory.search(query=msg, category=MemoryCategory.CONTEXT, limit=2)
                
                core_memories = []
                if raw_core_memories:
                    from ..model import SharedModelProvider
                    critic_model = SharedModelProvider.get_model(mode="brief")
                    
                    for anchor in raw_core_memories:
                        val = anchor.value if isinstance(anchor.value, str) else str(anchor.value)
                        
                        from ..prompts.registry import get_prompt_registry
                        eval_prompt = get_prompt_registry().get("system.critic.prompt", msg=msg, val=val)
                        try:
                            eval_res = await critic_model.think(eval_prompt, phase="brief")
                            if "YES" in eval_res.upper():
                                core_memories.append(anchor)
                            else:
                                logger.info(f"[MEMORY CRITIC] Loại bỏ Anchor Memory sai bối cảnh: {val[:50]}...")
                        except Exception:
                            core_memories.append(anchor)
                            
                # 2. Dijkstra-Inspired "Expansion" (Traverse related nodes)
                # If we found an Anchor Memory, we expand our search using its content 
                # to find older, deeply linked past context.
                if core_memories:
                    user_context += "\n### KNOWLEDGE PULLED FROM DEEP LONG-TERM MEMORY (MULTI-HOP):\n"
                    expanded_memories = []
                    
                    for anchor in core_memories:
                        val = anchor.value if isinstance(anchor.value, str) else str(anchor.value)
                        user_context += f"- [Anchor] {val[:300]}\n"
                        
                        # Hop 2: Search memory again using the anchor's content to find connected events
                        linked_memories = await memory.search(query=val[:100], category=MemoryCategory.CONTEXT, limit=1)
                        for link in linked_memories:
                            # Avoid duplicates
                            link_val = link.value if isinstance(link.value, str) else str(link.value)
                            if link_val not in user_context:
                                user_context += f"- [Dijkstra Hop] {link_val[:300]}\n"
                                
                # Auto-inject User Profile if the user talks about themselves
                prefs = await memory.search(query=f"preferences for {state['chat_id']} {msg}", category=MemoryCategory.USER_PROFILE, limit=2)
                if prefs:
                    user_context += f"\n### USER PROFILE ({settings.user_pronoun.upper()}):\n"
                    for p in prefs:
                        val = p.value if isinstance(p.value, str) else str(p.value)
                        if val not in user_context:
                            user_context += f"- {val[:150]}\n"
                            
            except Exception as e:
                logger.debug(f"[NEURAL_GENERATE] Dijkstra-Semantic recall failed: {e}")
        # ----------------------------------------------------------------

        msg = state["user_message"]
        
        logic = str(state.get("logic") or "")
        # Note: Noisy breadcrumbs are now isolated in 'associative_context' via observe.py

        logic = f"{logic}\n{user_context}".strip()
        state["logic"] = logic
        history = state.get("chat_history", [])
        
        # Phase 27: Associative context loading
        associative_context = state.get("associative_context", "None") or "None"
        task_outputs = state.get("task_outputs", [])
        plan = state.get("plan", [])
        thought = state.get("planning_thought", "")
        
        # Current Time for context
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Context for generation (Relaxed for GPU - Increased to {settings.context_generation_limit} messages)
        from memory.context import ConversationContextManager
        ctx_manager = ConversationContextManager(char_limit_per_message=8000, total_history_limit=50000)
        history_str = await ctx_manager.get_optimized_history(state["chat_id"], state["context"]["memory"], limit=settings.context_generation_limit)

        # Build Results String & Smart Compression
        results_str = ""
        prompt_mode = "pure_chat" # Default
        has_data_results = False

        if task_outputs:
            has_data_results = True
            raw_results_parts = []
            for i, res in enumerate(task_outputs):
                try:
                    task_info_raw = plan[i] if i < len(plan) else "Unknown Task"
                    task_info = task_info_raw.get("task", f"Task {i+1}") if isinstance(task_info_raw, dict) else str(task_info_raw)
                    
                    res_content = ""
                    if isinstance(res, dict):
                        # Detect Critic Override in results
                        if res.get("override") or res.get("action") == "IGNORE":
                            res_content = f"[INTERNAL_BLOCK] The Internal Critic blocked this action: {res.get('reason', 'Safety/Relevance check failed')}. Please apologize to the user and explain that you can't perform this specific lookup right now."
                        else:
                            # Extract core payload
                            payload = res.get("data") or res.get("content") or res.get("text")
                            if payload:
                                if isinstance(payload, (list, dict)):
                                    res_content = json.dumps(payload, indent=2, default=str)
                                else:
                                    res_content = str(payload)
                            else:
                                # Fallback if no specific data key
                                res_content = json.dumps(res, indent=2, default=str)
                    else:
                        res_content = str(res)

                    raw_results_parts.append(f"### RESULT FROM: {task_info}\n{res_content}")
                except Exception as e:
                    logger.error(f"[NEURAL_GENERATE] Error processing task output {i}: {e}")
            
            combined_results = "\n\n".join(raw_results_parts)
            
            # --- NGO: MICRO-SYNTHESIS (Sếp's "Main Points" reasoning) ---
            # Increased threshold from 2000 to 15000 to ensure tables aren't lost for small-medium results.
            if len(combined_results) > 15000:
                logger.info(f"[NEURAL_GENERATE] Large results detected ({len(combined_results)} chars). Compressing via Micro-Synthesis.")
                from ..model import SharedModelProvider
                from ..prompts.registry import get_prompt_registry
                model_prov = SharedModelProvider.get_model()
                p_reg = get_prompt_registry()
                
                # Use manager to compress results into main points (Phase 27 Associative Cog)
                # Specialized for data: use core.generator.data_compression
                results_str = await ctx_manager.compress_large_context(combined_results, model_prov, p_reg, query=msg, prompt_key="persona.generator.data_compression")

                # --- VECTOR DB INTEGRATION: Save raw results for future RAG ---
                memory = state["context"].get("memory")
                if memory:
                    try:
                        from memory.persistent import MemoryCategory
                        # Store in pieces if very large for better semantic granularity
                        import textwrap
                        storage_chunks = textwrap.wrap(combined_results, 4000)
                        for ic, rc in enumerate(storage_chunks[:5]): # Limit to first 5 chunks (20k chars) to avoid DB bloat
                            await memory.remember(
                                key=f"data_dump:{state['chat_id']}:{datetime.utcnow().timestamp()}:{ic}",
                                value=rc,
                                category=MemoryCategory.CONTEXT,
                                importance=0.4,
                                expires_in_days=14, # Keep for 2 weeks
                                embedding_text=f"Result for '{msg}': {rc[:500]}"
                            )
                        logger.info(f"[NEURAL_GENERATE] Raw results cached to Vector DB ({len(storage_chunks)} chunks).")
                    except Exception as e:
                        logger.debug(f"[NEURAL_GENERATE] Vector DB caching skipped: {e}")
            else:
                results_str = combined_results
            
            prompt_mode = "synthesis"
        else:
            # Dynamic Hallucination Guard: Use Speculator's intent detection instead of hardcoding
            spec_ctx = state.get("speculative_data_context", {})
            # Only trigger if Speculator saw data intent AND Router agreed it needed planning
            if spec_ctx.get("intent_detected") and state.get("needs_planning") and not task_outputs:
                logger.warning("[NEURAL_GENERATE] Hallucination Guard Triggered: Data intent detected by Speculator/Router but no tool results found.")
                # We mention the intent but don't fabricate results.
                results_str = "[INTERNAL_NOTICE] The requested data lookup was initiated but failed to return results. Do not hallucinate data."
                prompt_mode = "synthesis"
                has_data_results = True # Force synthesis mode to show the notice to the LLM
            
            if "không được tự bịa" in state.get("logic", ""):
                 state["logic"] = "" # Clear stale warning if it's already being handled by hallu guard logic


        # Final mode decision
        if state.get("needs_planning") or state.get("task_outputs"):
            prompt_mode = "synthesis"
            # NGO: Clear logic if we have data to avoid confusing the generator with legacy 
            # "failed to trigger tool" warnings from Router/Speculator.
            if "không được tự bịa" in state.get("logic", ""):
                 state["logic"] = ""
        elif state.get("is_fast_track"):
            prompt_mode = "fast_track"
        else:
            prompt_mode = "pure_chat"

        logger.debug(f"[NEURAL_GENERATE] Chosen Mode: {prompt_mode}")

        # --- VISUAL BYPASS DETECTION (Sếp's Request: Web Search = Text Only) ---
        skip_visuals = False
        # Identify if any task in the plan or results came from the WEB realm
        check_plan = plan if plan else []
        for task in (check_plan if isinstance(check_plan, list) else [check_plan]):
            if isinstance(task, dict):
                skill_name = str(task.get("skill", "")).lower()
                task_desc = str(task.get("task", "")).lower()
                if "web" in skill_name or "search" in skill_name or "web" in task_desc or "search" in task_desc:
                    skip_visuals = True
                    break
            elif isinstance(task, list): # Parallel wave
                for subtask in task:
                    if isinstance(subtask, dict):
                        sub_skill = str(subtask.get("skill", "")).lower()
                        sub_task_desc = str(subtask.get("task", "")).lower()
                        if "web" in sub_skill or "search" in sub_skill or "web" in sub_task_desc or "search" in sub_task_desc:
                            skip_visuals = True
                            break
                if skip_visuals: break

        logger.debug(f"[NEURAL_GENERATE] Skip Visuals: {skip_visuals}")

        from ..prompts.registry import get_prompt_registry
        p_registry = get_prompt_registry()

        msg = state.get("user_message", "")
        
        # --- NGO FIX: Clean up Objective for Prompt ---
        my_tag = f"@{getattr(settings, 'bot_username', 'bot')}"
        import re
        a2a_match = re.search(r'\[A2A_BUS: Message from (@[a-zA-Z0-9_]+)\]', msg)
        sender_peer = a2a_match.group(1) if a2a_match else None
        
        # Strip self tag so LLM isn't tempted to repeat it
        msg_for_prompt = msg.replace(my_tag, "").strip()
        
        if sender_peer:
            msg_for_prompt += f"\n\n(IMPORTANT: This message was forwarded from your peer bot {sender_peer}. You MUST reply directly to them by starting your message with {sender_peer})"
        bot_name = getattr(settings, 'bot_name', 'Brain')
        # Use the fresh peer_bot_map fetched at the start of the node. Only show @handles.
        peers_list = ", ".join([f"@{tag.lstrip('@')}" for name, tag in peer_bot_map.items()]) if peer_bot_map else "None"
        
        if prompt_mode == "fast_track":
            prompt = p_registry.get("persona.generator.fast_track", 
                                    msg=msg_for_prompt, 
                                    peers=peers_list,
                                    bot_name=bot_name,
                                    mood=state.get('mood', 'OPTIMISTIC'), 
                                    energy=f"{state.get('energy_level', 1.0)*100:.0f}%")
        elif prompt_mode == "pure_chat":
            prompt = p_registry.get("persona.generator.pure_chat", 
                                     current_time=current_time, 
                                     logic=logic, 
                                     history_str=history_str, 
                                     msg=msg_for_prompt, 
                                     peers=peers_list,
                                     associative_context=associative_context,
                                     user_pronoun=getattr(settings, 'user_pronoun', 'Sếp'),
                                     bot_name=bot_name,
                                     mood=state.get('mood', 'OPTIMISTIC'), 
                                     energy=f"{state.get('energy_level', 1.0)*100:.0f}%")
        else:
             # --- SYSTEM 2: SYNTHESIS (With Tool Results) ---
            logger.debug(f"[NEURAL_GENERATE] Mode: Synthesis with {len(task_outputs)} task outputs")
            
            prompt = p_registry.get("persona.generator.synthesis", 
                                     current_time=current_time, 
                                     logic=logic, 
                                     history_str=history_str, 
                                     user_message=state.get("user_message", ""),
                                     msg=msg_for_prompt, 
                                     peers=peers_list,
                                     thought=thought, 
                                     results_str=results_str, 
                                     associative_context=associative_context,
                                     bot_name=bot_name,
                                     mood=state.get('mood', 'OPTIMISTIC'), 
                                     energy=f"{state.get('energy_level', 1.0)*100:.0f}%")

        # DEBUG: Log prompt component sizes
        logger.debug(f"[GENERATE DEBUG] History Size: {len(history_str)}")
        logger.debug(f"[GENERATE DEBUG] Results Size: {len(results_str)}")
        logger.debug(f"[GENERATE DEBUG] User Context Size: {len(user_context)}")
        
        # DEEP DEBUG: Dump input data and prompts
        logger.debug(f"[GENERATE DEEP DEBUG] Logic State: '{state.get('logic', '')}'")
        logger.debug(f"[GENERATE DEEP DEBUG] Has Valid Data Results: {has_data_results}")
        if has_data_results:
             logger.debug(f"[GENERATE DEEP DEBUG] Results Preview: {results_str[:500]}...")
             
        # logger.debug(f"--- PROMPT DUMP ---\n{prompt[:500]}...\n--- END DUMP ---")

        # --- SAFETY CHECK: Prompt Size vs Context Window ---
        # 32k context size (GPU) ~= 100k+ chars. 
        # Safety buffer: limit prompt to 80k chars.
        if len(prompt) > 80000:
            logger.warning(f"[NEURAL_GENERATE] PROMPT TOO LARGE ({len(prompt)} chars). Truncating results component.")
            
            # Smart truncation: Keep system prompt & history, cut results
            excess = len(prompt) - 80000
            if len(results_str) > excess + 1000:
                results_str = results_str[:-(excess + 2000)] + "\n... [RESULTS TRUNCATED DUE TO CONTEXT LIMIT]"
                
                # Re-build prompt with truncated results
                prompt = p_registry.get("persona.generator.synthesis", 
                                     current_time=current_time, 
                                     logic=state.get('logic', ''), 
                                     history_str=history_str, 
                                     user_message=state.get("user_message", ""),
                                     msg=msg_for_prompt, 
                                     peer_username=state.get("peer_username", "Unknown"),
                                     thought=thought, 
                                     results_str=results_str, 
                                     bot_name=bot_name,
                                     mood=state.get('mood', 'OPTIMISTIC'), 
                                     energy=f"{state.get('energy_level', 1.0)*100:.0f}%")
                logger.info(f"[NEURAL_GENERATE] Prompt resized to {len(prompt)} chars.")

        logger.debug(f"[NEURAL_GENERATE] Prompt ready (Size: {len(prompt)} chars). Calling LLM model.think...")
        model = GeneratorModel()
        response = await model.think(prompt, phase="synthesis", mood=state.get('mood', 'OPTIMISTIC'), energy=state.get('energy_level', 1.0))
        
        if response == "ERROR_TIMEOUT":
            state["response"] = "I apologize, my memory is currently a bit 'clogged' while synthesizing information. Please try again! 🧠💨"
            state["phase"] = "completed"
            return state
        elif response == "ERROR_FAILED":
            state["response"] = "I apologize, I'm experiencing some technical difficulties while preparing your answer. 🧠🛠️"
            state["phase"] = "completed"
            return state

        # 🛡️ DEFENSIVE: Ensure response is a string
        # NGO: Handle AIMessage from ChatOllama
        from ..utils import get_llm_content
        response = get_llm_content(response)
        
        if not isinstance(response, str):
            logger.warning(f"[NEURAL_GENERATE] Response is not a string, it is {type(response)}")
            response = str(response)

        # NGO: Strip thinking tags for user-facing response
        from ..utils import strip_thinking_tags
        response = strip_thinking_tags(response)

        final_response = response.replace("Niva:", "").replace("Assistant:", "").strip()
        
        # --- NGO FIX: Prevent self-tagging ---
        my_tag = f"@{getattr(settings, 'bot_username', 'bot')}"
        if isinstance(final_response, str):
            final_response = final_response.replace(my_tag, "").strip()
        elif isinstance(final_response, dict) and "text" in final_response:
            final_response["text"] = final_response["text"].replace(my_tag, "").strip()
        
        # Attach photo if present in task outputs (Check both top-level and nested 'data')
        for res in task_outputs:
            if not isinstance(res, dict):
                continue
                
            photo_data = res.get("photo")
            if not photo_data and isinstance(res.get("data"), dict):
                photo_data = res["data"].get("photo")
                
            if photo_data:
                logger.info("[NEURAL_GENERATE] Found photo in task results, attaching to response.")
                try:
                    cap = final_response[:1000] if isinstance(final_response, str) else str(final_response)[:1000]
                    final_response = {
                        "text": final_response if isinstance(final_response, str) else final_response.get("text", str(final_response)),
                        "photo": photo_data,
                        "caption": cap
                    }
                except Exception as e:
                    logger.error(f"[DEBUG_GENERATE] Error creating final_response dict: {e}")
                break

        state["response"] = final_response
        
        # Guard against empty response
        if not response:
            logger.warning("[NEURAL_GENERATE] Final response is empty. Using fallback.")
            state["response"] = "System check: The processing completed but returned an empty result. Please check logs or rephrase your request."
            final_response = state["response"]
        
        # --- NEW: Visual Enhancement (Unified for first-time and cache) ---
        state["response"] = await enhance_response(state["response"], user_message=state.get("user_message", ""), skip_visuals=skip_visuals)
        
        # No persona hotfix applied as requested for future flexibility
        
        # --- NEW: DLP Scrubbing (Final Guard) ---
        from utils.security import SecurityShield
        if isinstance(state["response"], str):
            state["response"] = SecurityShield.scrub_sensitive_output(state["response"])
        elif isinstance(state["response"], dict) and "text" in state["response"]:
            state["response"]["text"] = SecurityShield.scrub_sensitive_output(state["response"]["text"])
            if "caption" in state["response"]:
                state["response"]["caption"] = SecurityShield.scrub_sensitive_output(state["response"]["caption"])
        
        # --- PHASE 15.4: Response Embedding for CIE Tier 2 ---
        try:
            response_text = state["response"]
            if isinstance(response_text, dict):
                response_text = response_text.get("text", str(response_text))
            if isinstance(response_text, str) and len(response_text) > 20:
                from utils.embeddings import get_embedding_engine
                resp_engine = get_embedding_engine()
                state["response_vector"] = await resp_engine.get_embedding(response_text[:500])
                logger.debug("[PHASE 15.4] Response embedding computed for CIE Tier 2.")
        except Exception as e:
            logger.debug(f"[PHASE 15.4] Response embedding failed (non-critical): {e}")
        # -----------------------------------------------

        
        # --- SHORT-TERM MEMORY CACHE SAVE (Vector) ---
        memory = state["context"].get("short_memory")
        q_vec = state.get("query_vector")
        
        if memory and q_vec:
             # Boss's Request: Strip binary 'photo'/'image' to save memory
            resp_to_cache = state["response"]
            if isinstance(resp_to_cache, dict):
                # We only cache the text part, redraw on hit
                resp_to_cache = {k: v for k, v in resp_to_cache.items() if k not in ["photo", "image", "caption"]}
            
            try:
                memory.set_cache(q_vec, resp_to_cache, state["user_message"])
                logger.debug(f"[BRAIN] Saved optimized (text-only) response to Smart Vector Cache")
            except Exception as e:
                logger.warning(f"[BRAIN] Failed to save to Cache: {e}")
        # ---------------------------------------------
        
        # Record in Long-Term Memory
        long_memory = state["context"].get("memory")
        if long_memory:
            try:
                text_log = final_response
                if isinstance(final_response, dict):
                    text_log = final_response.get("text", final_response)
                await long_memory.record_chat_message(state["chat_id"], "assistant", str(text_log))
            except Exception as e:
                logger.error(f"[DEBUG_GENERATE] Error recording to memory: {e}")
        
    except Exception as e:
        logger.error(f"[GENERATE] Failed: {e}")
        state["response"] = "I'm having a bit of trouble synthesizing the information. Please wait a moment."
        import traceback
        logger.error(traceback.format_exc())
        
    state["phase"] = "generated"
    return state
