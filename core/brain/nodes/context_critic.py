import re
from core.brain.state import ChatState
from core.brain.model import BrainModel
from core.brain.prompts.registry import get_prompt_registry
from utils.logger import get_logger

logger = get_logger()

async def context_critic_node(state: ChatState) -> ChatState:
    """
    CONTEXT CRITIC: Brain V2.6 security gate to ensure context sufficiency.
    Checks if we have enough info to answer or if we should ask for clarification/escalate.
    """
    logger.debug("[CONTEXT_CRITIC] auditing context sufficiency...")

    if state.get("final_decision") == "PLAN":
        logger.info("[CONTEXT_CRITIC] Bypassing audit: Brain is in PLANNING mode. Context will be research-driven.")
        return state # Already planning, context will be fetched by tools
    
    try:
        model = BrainModel(mode="critic")
        registry = get_prompt_registry()
        
        msg = state.get("user_message", "")
        # Get full session history available in state
        history = state.get("chat_history", [])
        memory_context = state.get("associative_context", "")
        
        context_str = f"History (Session): {history}\n\nMemory Context: {memory_context}"
        
        prompt = registry.get(
            "system.critic.context_critic",
            msg=msg,
            context_str=context_str
        )
        
        eval_result = await model.think(prompt, phase="context_audit")
        
        # Enhanced parsing using regex for structured output
        decision_match = re.search(r"Decision\s*:\s*\[?(YES|NO)\]?", eval_result, re.IGNORECASE)
        reason_match = re.search(r"Reason\s*:\s*(.*)", eval_result, re.IGNORECASE)
        
        decision = decision_match.group(1).upper() if decision_match else "YES"
        reason = reason_match.group(1).strip() if reason_match else "No reason provided"
        
        if decision == "NO":
            logger.info(f"[CONTEXT_CRITIC] ⚠️ Context Insufficient. Reason: {reason}")
            state["thoughts"].append(f"Context Critic: Found gap - {reason}")
            
            # If context is bad, nudge towards a clarifying question
            if any(kw in reason.lower() for kw in ["missing", "don't know", "what is", "insufficient"]):
                 # Add a logic hint for the generator
                 state["logic"] = f"{state.get('logic', '')}\nNOTICE: Context Critic found a gap: {reason}. Ask for clarification if needed.".strip()
        
    except Exception as e:
        logger.error(f"[CONTEXT_CRITIC] Failed: {e}")
    
    return state
