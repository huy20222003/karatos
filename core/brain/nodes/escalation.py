import re
from core.brain.state import ChatState
from core.brain.model import BrainModel
from core.brain.prompts.registry import get_prompt_registry
from utils.logger import get_logger
from datetime import datetime

logger = get_logger()

async def chat_escalation_node(state: ChatState) -> ChatState:
    """
    ESCALATION CHECK: Determine if the CHAT response is sufficient or 
    needs to be escalated to PLAN mode (Brain V2.6).
    """
    # Only run for CHAT intent at escalation level 0
    if state.get("final_decision") != "CHAT" or state.get("escalation_level", 0) > 0:
        return state
    
    # Do not escalate if tools were already used (e.g. implicit tools)
    if state.get("task_outputs"):
        return state

    logger.debug("[ESCALATION] Checking if CHAT response needs escalation...")
    
    try:
        # Get context data
        msg = state.get("user_message", "")
        response_text = state.get("response", "")
        intent_hint = state.get("intent", "General")
        model = BrainModel(mode="critic")

        # Get identity from state context
        identity = state.get("context", {}).get("identity")
        bot_name = identity.active_name if identity and identity.active_name else "Niva"
        
        registry = get_prompt_registry()
        # Format the prompt
        prompt = registry.get(
            "system.router.escalation_check",
            msg=msg,
            response=response_text,
            intent_hint=intent_hint,
            bot_name=bot_name
        )
        
        # Query the critic
        eval_result = await model.think(prompt, phase="escalation_check")
        
        # Enhanced Parsing for Decision, Confidence, Reason, Gap
        decision_match = re.search(r"Decision\s*:\s*\[?(YES|NO)\]?", eval_result, re.I)
        confidence_match = re.search(r"Confidence\s*:\s*\[?(HIGH|MEDIUM|LOW)\]?", eval_result, re.I)
        reason_match = re.search(r"Reason\s*:\s*(.*)", eval_result, re.I)
        gap_match = re.search(r"Gap\s*:\s*(.*)", eval_result, re.I)

        decision = decision_match.group(1).upper() if decision_match else ("YES" if "[YES]" in eval_result.upper() else "NO")
        reason = reason_match.group(1).strip() if reason_match else "Critic requested escalation"
        gap = gap_match.group(1).strip() if gap_match else "None"
        
        if decision == "YES":
            logger.warning(f"[ESCALATION] ⬆️ Escalating CHAT -> PLAN. Reason: {reason} | Gap: {gap}")
            
            # Pivot the state
            state["final_decision"] = "PLAN"
            state["escalation_level"] += 1
            state["decision_history"].append({
                "decision": "PLAN",
                "reason": f"Escalated from CHAT: {reason}",
                "at_node": "chat_escalation_node",
                "timestamp": datetime.now().isoformat()
            })
            
            # Reset response and thoughts for the planning phase
            state["response"] = None
            state["thoughts"].append(f"Escalation: Pivoted to PLAN. Reason: {reason}")
            if gap != "None":
                state["thoughts"].append(f"Escalation Gap Detected: {gap}")
                # Inject gap into logic for the next planner run
                state["logic"] = f"{state.get('logic', '')}\n[ESCALATION_GUIDANCE]: {gap}".strip()
            
        else:
            logger.debug("[ESCALATION] 🟢 CHAT response deemed sufficient.")
            
    except Exception as e:
        logger.error(f"[ESCALATION] Check failed: {e}")
        # Fail-safe: continue as CHAT
    
    return state
