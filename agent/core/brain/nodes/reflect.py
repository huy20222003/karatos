from ..state import ChatState
from utils.logger import get_logger

logger = get_logger()

async def chat_reflect_node(state: ChatState) -> ChatState:
    """
    METACOGNITION ENGINE (Phase 15.3)
    
    Self-awareness node that closes the learning loop:
    1. PPF Accuracy Feedback — was the routing prediction correct?
    2. ACR Weight Tuning — adapt signal weights based on outcome
    3. CIE Correction Signal — record if response was corrected
    4. Feedback Bus Emission — publish full interaction signal
    5. Mood Evolution — evolve agent personality based on interaction
    """
    try:
        from core.identity import AgentIdentity
        from ..algorithms.feedback_bus import get_feedback_bus
        
        identity = AgentIdentity()
        identity.current_mood = state.get("mood", "OPTIMISTIC")
        identity.energy = state.get("energy_level", 1.0)
        bus = get_feedback_bus()
        
        # ====================================
        # 1. DETERMINE INTERACTION OUTCOME
        # ====================================
        has_error = bool(state.get("error"))
        was_corrected = any("Self-Correction" in t for t in state.get("thoughts", []))
        has_response = bool(state.get("response"))
        
        # Heuristic: interaction is "correct" if no error and response was generated
        was_correct = has_response and not has_error
        
        # ====================================
        # 2. PPF ACCURACY FEEDBACK
        # ====================================
        ppf_features = state.get("_ppf_features")
        if ppf_features:
            # Find what PPF predicted vs what actually happened
            routing_thought = next(
                (t for t in state.get("thoughts", []) if "Router:" in t), ""
            )
            
            # If CIE corrected the response, the routing might have been suboptimal
            if was_corrected:
                logger.info("[METACOGNITION] ⚠️ CIE corrected the response — signaling suboptimal routing to PPF.")
                # Don't re-record to PPF (already recorded in router), but emit signal
                bus.emit("CORRECTION", {
                    "was_corrected": True,
                    "routing_thought": routing_thought[:200],
                }, source="reflect")
        
        # ====================================
        # 3. ACR WEIGHT ADAPTATION
        # ====================================
        try:
            from ..algorithms.confidence_engine import get_confidence_engine
            acr = get_confidence_engine()
            acr.record_query(
                state.get("user_message", ""),
                decision="OUTCOME",
                was_correct=was_correct,
            )
        except Exception as e:
            logger.debug(f"[METACOGNITION] ACR feedback failed: {e}")
        
        # ====================================
        # 4. FEEDBACK BUS — Full Interaction Signal
        # ====================================
        bus.emit("INTERACTION", {
            "user_message": state.get("user_message", "")[:200],
            "was_correct": was_correct,
            "was_corrected": was_corrected,
            "had_error": has_error,
            "routing_method": _extract_routing_method(state.get("thoughts", [])),
            "mood": identity.current_mood,
            "phase_trace": _build_phase_trace(state.get("thoughts", [])),
        }, source="reflect")
        
        # ====================================
        # 5. MOOD EVOLUTION
        # ====================================
        outcome = "success" if was_correct else "failure"
        identity.evolve_mood("USER_CHAT", outcome)
        
        state["mood"] = identity.current_mood
        state["energy_level"] = identity.energy
        
        logger.info(
            f"[METACOGNITION] 🧠 Cycle complete | "
            f"Correct={was_correct} | Corrected={was_corrected} | "
            f"Mood={state['mood']} | Energy={state['energy_level']:.0%}"
        )
        
    except Exception as e:
        logger.error(f"[METACOGNITION] Reflection failed: {e}")
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

