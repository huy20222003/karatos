import json
from typing import Dict, Any
from core.brain.state import ChatState
from core.brain.utils import extract_json
from core.brain.model import BrainModel
from utils.logger import get_logger

logger = get_logger()

class ResultCriticModel(BrainModel):
    def __init__(self):
        super().__init__(mode="brief")

async def result_critic_node(state: ChatState) -> ChatState:
    """
    LLM-based Result Critic: Analyzes the tool output and decides if re-planning is needed.
    """
    action_result = state.get("action_result")
    active_task = state.get("active_task")
    
    if not action_result or not active_task:
        state["phase"] = "result_critic_skipped"
        return state

    # Identify if there's an error in the result
    has_error = False
    if isinstance(action_result, dict):
        if action_result.get("status") == "error":
            has_error = True
    elif isinstance(action_result, str) and "ERROR" in action_result.upper():
        has_error = True
    
    # If it looks like success, skip LLM analysis to save tokens (Optimization)
    if not has_error:
        state["phase"] = "result_critic_done"
        return state

    # Limit retries to prevent infinite loops (Phase 36)
    if state.get("retry_count", 0) >= 3:
        logger.warning(f"[SELF-HEALING] Max retries reached for {active_task.get('task')}. Giving up.")
        state["phase"] = "result_critic_failed"
        return state

    logger.thought("AI is analyzing the tool failure for Self-Healing...")

    from core.brain.prompts.registry import get_prompt_registry
    registry = get_prompt_registry()
    
    # Context extraction
    tool_name = active_task.get("task", "Unknown")
    params = json.dumps(active_task.get("params", {}), ensure_ascii=False)
    result_str = str(action_result)
    
    prompt = registry.get(
        "system.critic.result_logic",
        user_message=state["user_message"],
        tool_name=tool_name,
        params=params,
        result=result_str,
        current_step=state.get("current_step", 0),
        total_steps=len(state.get("plan", [])),
        retry_count=state.get("retry_count", 0)
    )

    model = ResultCriticModel()
    analysis_raw = await model.think(prompt, phase="brief")
    analysis = extract_json(analysis_raw) or {}

    if analysis.get("should_replan"):
        logger.info(f"[SELF-HEALING] LLM suggests RE-PLAN: {analysis.get('critique')}")
        state["replan_context"] = analysis.get("replan_context")
        state["retry_count"] = state.get("retry_count", 0) + 1
        state["phase"] = "replan_required"
    else:
        logger.info(f"[SELF-HEALING] LLM suggests giving up or success: {analysis.get('critique')}")
        state["phase"] = "result_critic_done"

    return state
