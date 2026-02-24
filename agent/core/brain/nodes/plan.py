from ..state import ChatState
from core.identity import AgentIdentity
from config.settings import settings
from utils.logger import get_logger
from langchain_ollama import ChatOllama
from utils.logger import get_logger

logger = get_logger()

from ..model import SharedModelProvider, BrainModel
from langchain_core.tools import tool

@tool
def create_plan(steps: list[dict]) -> str:
    """Define a multi-step sequence of tasks to accomplish the user request.
    
    Args:
        steps: A list of step objects. Each step should contain:
            - thought: Reasoning for why this step is necessary.
            - task: The exact name of the skill/tool to use (must match the provided tools list).
            - params: Dictionary of key-value pairs representing inputs for the skill.
            - confidence: Estimation of step success/safety (0.0 to 1.0).
    """
    pass

class PlannerModel(BrainModel):
    def __init__(self):
        super().__init__(mode="planning")

    async def think(self, prompt: str, phase: str = "planning", mood: str = "OPTIMISTIC", energy: float = 1.0, tools: list = None) -> str:
        # Longer timeout for planning
        return await super().think(prompt, phase=phase, mood=mood, energy=energy, timeout=300.0, tools=tools)

async def chat_plan_node(state: ChatState) -> ChatState:
    """
    NEURAL PLANNING: Analyze request and create a multi-step plan.
    """
    
    if state.get("plan"):
        logger.info("[PLANNER] Skipping planning (Reflex plan already exists)")
        state["phase"] = "planned"
        return state

    msg = state["user_message"]
    history = state["chat_history"]
    from skills.registry import get_skill_registry
    registry = get_skill_registry()
    
    # Contextual awareness: Optimized history (Summary + Recent) via ContextManager
    from memory.context import ConversationContextManager
    ctx_manager = ConversationContextManager(char_limit_per_message=1000, total_history_limit=3000)
    history_str = await ctx_manager.get_optimized_history(state["chat_id"], state["context"]["memory"], limit=settings.context_planning_limit)

    # --- FULL CONTEXT: Enable all tools for strategic planning ---
    tool_schemas = await registry.get_tool_schemas()
    skills_list = []
    for s in tool_schemas:
        params_str = ""
        if s.get("parameters") and s["parameters"].get("properties"):
            params_str = " (params: " + ", ".join(s["parameters"]["properties"].keys()) + ")"
        skills_list.append(f"- {s['name']}{params_str}: {s['description']}")
    
    skills_json = "\n".join(skills_list)
    
    # --- PEER AWARENESS: Fetch co-workers for A2A coordination ---
    peers_str = "None"
    try:
        from skills.mcp_realm import get_mcp_realm
        mcp = get_mcp_realm()
        peer_bot_map = await mcp.get_bot_registrations()
        if peer_bot_map:
            peers_str = ", ".join([f"@{tag} ({name})" for name, tag in peer_bot_map.items()])
    except:
        pass

    from ..prompts.registry import get_prompt_registry
    p_registry = get_prompt_registry()
    
    my_username = f"@{getattr(settings, 'bot_username', '')}"

    prompt = p_registry.get("system.planner.planning_logic", 
                             msg=msg, 
                             history_str=history_str, 
                             skills_json=skills_json, 
                             peers=peers_str,
                             chat_id=str(state["chat_id"]),
                             bot_name=getattr(settings, 'bot_name', 'SystemBot'),
                             my_username=my_username,
                             mood=state.get('mood', 'OPTIMISTIC'), 
                             energy=f"{state.get('energy_level', 1.0)*100:.0f}%")

    model = PlannerModel()
    # Use native tool calling for planning
    logger.debug(f"[PLANNER_DEBUG] Sending prompt to LLM (Prompt Length: {len(prompt)} chars)...")
    tool_calls = await model.think(prompt, phase="planning", mood=state.get('mood', 'OPTIMISTIC'), energy=state.get('energy_level', 1.0), tools=[create_plan])
    
    from ..utils import parse_tool_call_robust
    # Pass current state confidence as base for auto-wrapping
    tool_args = parse_tool_call_robust(tool_calls, "create_plan", base_confidence=state.get("confidence", 0.0))
    plan = tool_args.get("steps", [])

            
    if not isinstance(plan, list):
        # Emergency debug for real malformed output
        from ..utils import get_llm_content
        raw_content = get_llm_content(tool_calls)
        logger.error(f"[PLANNER_FATAL] Model returned malformed content. Raw Snippet: {raw_content[:200]}")
        state["planning_thought"] = "Planning failed (malformed output)."
        state["needs_planning"] = False
    elif not plan:
        # Planner intentionally decided no tool is needed (e.g. Rule IV in planner.yaml)
        logger.info(f"[PLANNER] Model decided no tools are needed for this request.")
        state["planning_thought"] = "Planner decided no tool-based actions are required."
        state["needs_planning"] = False
    else:
        state["plan"] = plan
        state["current_step"] = 0
        state["task_outputs"] = []
        state["planning_thought"] = f"Created plan with {len(plan)} steps via Robust Tool Extraction."
        
    state["phase"] = "planned"
    return state


async def chat_prepare_step_node(state: ChatState) -> ChatState:
    """
    PREPARE STEP: Get the next task from the plan ready for execution.
    """
    plan = state.get("plan", [])
    current_step = state.get("current_step", 0)
    
    if current_step < len(plan):
        task = plan[current_step]
        state["decision"] = task # Set current decision/task
        
        # Safe logging for both single task (dict) and parallel wave (list)
        if isinstance(task, list):
            task_names = [t.get('task', t.get('thought', 'SubTask')) for t in task if isinstance(t, dict)]
            logger.info(f"[EXECUTOR] Preparing Wave {current_step + 1}/{len(plan)}: {len(task)} parallel tasks -> {', '.join(task_names)}")
        else:
            thought = task.get('thought', task.get('task', 'Executing...'))
            logger.info(f"[EXECUTOR] Preparing Step {current_step + 1}/{len(plan)}: {thought}")
    else:
        state["decision"] = None
        
    return state
