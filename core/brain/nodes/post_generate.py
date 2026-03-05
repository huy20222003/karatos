"""
Post-Generate Node — Combined Self-Correction + Reflection (Phase 3 Optimization)

Merges the previously separate self_correction and reflect nodes into one.
This reduces graph complexity (11 → 9 nodes) and eliminates one graph transition.

Flow: generate → post_generate → END
(Previously: generate → self_correction → reflect → END)
"""
from core.brain.state import ChatState
from core.identity import AgentIdentity
from utils.logger import get_logger

logger = get_logger()


async def chat_post_generate_node(state: ChatState) -> ChatState:
    """
    POST-GENERATE: Combined Self-Correction + Metacognition in a single node.
    
    Part 1 (Self-Correction): Validate draft response, fix tone/errors via CIE.
    Part 2 (Reflect): Update PPF, ACR, mood, emit feedback signals.
    """
    
    # ====================================================
    # PART 1: SELF-CORRECTION (formerly self_correction.py)
    # ====================================================
    
    # Short-circuit: Skip correction for fast-track or data results
    skip_correction = False
    
    if state.get("is_fast_track"):
        logger.info("[POST_GENERATE] Skipping self-correction for Fast-Track path.")
        skip_correction = True
    
    if not skip_correction:
        task_outputs = state.get("task_outputs", [])
        for res in task_outputs:
            if isinstance(res, dict) and res.get("status") == "success" and res.get("data"):
                logger.info("[POST_GENERATE] Skipping self-correction for successful data results.")
                skip_correction = True
                break

    draft = state.get("response")
    was_corrected = False
    
    if not skip_correction and draft and isinstance(draft, str):
        try:
            from core.brain.algorithms.cascade_evaluator import get_cascade_evaluator
            from core.brain.algorithms.feedback_bus import get_feedback_bus
            
            cascade = get_cascade_evaluator()
            bus = get_feedback_bus()
            
            result = await cascade.evaluate(
                user_message=state["user_message"],
                response=draft,
                query_vector=state.get("query_vector"),
                response_vector=state.get("response_vector"),
                mood=state.get("mood", "OPTIMISTIC"),
                energy=state.get("energy_level", 1.0),
            )
            
            if result["corrections"]:
                logger.info(f"[POST_GENERATE] CIE corrected at Tier {result['tier_exited']}. Reason: {result['reason']}")
                state["response"] = result["corrections"]
                state["thoughts"].append(f"Self-Correction (CIE Tier {result['tier_exited']}): {result['reason']}")
                was_corrected = True
                
                bus.emit("CORRECTION", {
                    "was_corrected": True,
                    "tier": result["tier_exited"],
                    "reason": result["reason"],
                }, source="post_generate")
            else:
                logger.info(f"[POST_GENERATE] CIE approved at Tier {result['tier_exited']}.")
                bus.emit("CORRECTION", {
                    "was_corrected": False,
                    "tier": result["tier_exited"],
                }, source="post_generate")
        except Exception as e:
            logger.warning(f"[POST_GENERATE] Self-correction failed: {e}")
    
    # ====================================================
    # PART 2: METACOGNITION / REFLECT (formerly reflect.py)
    # ====================================================
    try:
        from core.brain.algorithms.feedback_bus import get_feedback_bus
        from core.brain.algorithms.confidence_engine import get_confidence_engine
        
        # Use cached identity or create new
        identity = state.get("context", {}).get("identity")
        if not identity:
            identity = AgentIdentity()
        identity.current_mood = state.get("mood", "OPTIMISTIC")
        identity.energy = state.get("energy_level", 1.0)
        bus = get_feedback_bus()
        
        # 1. Determine interaction outcome
        has_error = bool(state.get("error"))
        has_response = bool(state.get("response"))
        was_correct = has_response and not has_error
        
        # 2. PPF Accuracy Feedback
        ppf_features = state.get("_ppf_features")
        if ppf_features and was_corrected:
            routing_thought = next(
                (t for t in state.get("thoughts", []) if "Router:" in t), ""
            )
            logger.info("[POST_GENERATE] CIE corrected — signaling suboptimal routing to PPF.")
            bus.emit("CORRECTION", {
                "was_corrected": True,
                "routing_thought": routing_thought[:200],
            }, source="reflect")
        
        # 3. ACR Weight Adaptation
        try:
            acr = get_confidence_engine()
            acr.record_query(
                state.get("user_message", ""),
                decision="OUTCOME",
                was_correct=was_correct,
            )
        except Exception as e:
            logger.debug(f"[POST_GENERATE] ACR feedback failed: {e}")
        
        # 4. Feedback Bus — Full Interaction Signal
        bus.emit("INTERACTION", {
            "user_message": state.get("user_message", "")[:200],
            "was_correct": was_correct,
            "was_corrected": was_corrected,
            "had_error": has_error,
            "routing_method": _extract_routing_method(state.get("thoughts", [])),
            "mood": identity.current_mood,
            "phase_trace": _build_phase_trace(state.get("thoughts", [])),
        }, source="post_generate")
        
        # 5. Mood Evolution
        outcome = "success" if was_correct else "failure"
        identity.evolve_mood("USER_CHAT", outcome)
        
        state["mood"] = identity.current_mood
        state["energy_level"] = identity.energy

        # --- METACOGNITIVE MEMORY: Learning from this interaction ---
        # Like a human reflecting "what did I learn?" after a conversation
        logic_structured = state.get("logic_structured", [])
        try:
            from memory.persistent import MemoryCategory
            meta_memory = state.get("context", {}).get("memory")
            chat_id = state.get("chat_id", "unknown")
            user_msg = state.get("user_message", "")
            
            if meta_memory:
                reflect_nodes = []
                
                # REFLECTION: Record lesson when self-correction happened
                if was_corrected:
                    from datetime import datetime
                    lesson = f"Self-corrected response to '{user_msg[:80]}'. Original had issues that needed fixing."
                    await meta_memory.remember(
                        f"reflection:{chat_id}:{datetime.utcnow().timestamp()}",
                        lesson,
                        category=MemoryCategory.REFLECTION,
                        importance=0.6
                    )
                    reflect_nodes.append({"content": "Learned from self-correction: response quality improved", "badge": "Reflection"})
                    logger.info("[POST_GENERATE] 🪞 Metacognition: Stored self-correction reflection")
                
                # SENTIMENT: Track emotional state over time
                from datetime import datetime
                sentiment_entry = f"Mood: {identity.current_mood}, Energy: {identity.energy:.0%}, Outcome: {outcome}"
                await meta_memory.remember(
                    f"sentiment:{chat_id}:{datetime.utcnow().timestamp()}",
                    sentiment_entry,
                    category=MemoryCategory.SENTIMENT,
                    importance=0.3,
                    expires_in_days=7
                )
                reflect_nodes.append({"content": sentiment_entry, "badge": "Sentiment"})
                
                # EXPERIENCE: Record successful interactions as positive experiences
                if was_correct and not has_error and len(user_msg) > 10:
                    exp_summary = f"Successfully handled: '{user_msg[:100]}' via {'planning' if state.get('plan') else 'direct chat'}"
                    await meta_memory.remember(
                        f"exp:{chat_id}:{datetime.utcnow().timestamp()}",
                        exp_summary,
                        category=MemoryCategory.EXPERIENCE,
                        importance=0.4,
                        expires_in_days=30
                    )
                    reflect_nodes.append({"content": exp_summary[:150], "badge": "Experience"})
                
                if reflect_nodes:
                    logic_structured.append({
                        "category": "Metacognition",
                        "icon": "fas fa-brain",
                        "nodes": reflect_nodes
                    })
                    state["logic_structured"] = logic_structured
                    
        except Exception as e:
            logger.debug(f"[POST_GENERATE] Metacognitive memory update failed: {e}")
        
        logger.info(
            f"[POST_GENERATE] Cycle complete | "
            f"Correct={was_correct} | Corrected={was_corrected} | "
            f"Mood={state['mood']} | Energy={state['energy_level']:.0%}"
        )
        
    except Exception as e:
        logger.error(f"[POST_GENERATE] Reflection failed: {e}")
        import traceback
        logger.error(traceback.format_exc())
    
    state["cycle_complete"] = True
    state["phase"] = "completed"
    return state


def _extract_routing_method(thoughts: list[str]) -> str:
    """Extract which routing method was used from thought log."""
    for t in thoughts:
        if "ACR auto-routed" in t:
            return "ACR_AUTO"
        if "PPF predicted" in t:
            return "PPF_BYPASS"
        if "Semantic match" in t:
            return "SEMANTIC_INTENT"
        if "Logic path" in t:
            return "LLM"
    return "UNKNOWN"


def _build_phase_trace(thoughts: list[str]) -> list[str]:
    """Build a compact trace of phases from thought log."""
    phases = []
    for t in thoughts:
        if "Router:" in t:
            phases.append("route")
        elif "Self-Correction" in t:
            phases.append("correction")
        elif "Plan:" in t:
            phases.append("plan")
    return phases
