from core.brain.state import ChatState
from core.identity import AgentIdentity
from config.settings import settings
from utils.logger import get_logger
from langchain_ollama import ChatOllama
from utils.logger import get_logger

logger = get_logger()

from core.brain.model import SharedModelProvider, BrainModel
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

    # --- INLINE CAPABILITY SELECTION (Phase 2: replaces separate scanner LLM call) ---
    # Lightweight keyword matching to pre-filter tools — no LLM overhead.
    # The planner still sees all tools but relevant ones are prioritized.
    tool_schemas = await registry.get_tool_schemas()
    
    msg_lower = msg.lower()
    msg_words = set(msg_lower.split())
    
    def _tool_relevance_score(schema: dict) -> int:
        """Simple keyword relevance score — no LLM needed."""
        score = 0
        name = schema.get("name", "").lower()
        desc = schema.get("description", "").lower()
        aliases = [a.lower() for a in schema.get("aliases", [])]
        
        # Check if tool name or key description words appear in user message
        if name in msg_lower or any(a in msg_lower for a in aliases):
            score += 3
        for word in name.replace("_", " ").split():
            if word in msg_words and len(word) > 2:
                score += 2
        for alias in aliases:
            if alias in msg_words:
                score += 2
        for word in msg_words:
            if len(word) > 3 and word in desc:
                score += 1
        return score
    
    # Score all tools
    scored = [(s, _tool_relevance_score(s)) for s in tool_schemas]
    relevant = [s for s, score in scored if score > 0]
    
    if relevant and len(relevant) < len(tool_schemas):
        # Show relevant tools first, then remaining (planner sees all but focused)
        remaining = [s for s, score in scored if score == 0]
        tool_schemas = relevant + remaining
        logger.info(f"[PLANNER] Inline capability filter: {len(relevant)} relevant / {len(tool_schemas)} total.")
    
    # Use enriched capabilities for the final prompt injection
    skills_json = registry.get_enriched_capabilities()
    
    # --- PEER AWARENESS: Use cached peer bot map (Entity-based Brain 3.1) ---
    my_name = (getattr(settings, 'bot_name', '') or '').lower()
    my_username = (getattr(settings, 'bot_username', '') or '').lower().lstrip('@')
    
    peer_items = []
    peer_bot_map = state.get("context", {}).get("peer_bot_map", {})
    for name, data in peer_bot_map.items():
        # Handle both legacy str and new dict format for robustness
        tag = data.get("tag", f"@{name}") if isinstance(data, dict) else f"@{data}"
        desc = data.get("description", "Independent Agent.") if isinstance(data, dict) else "Independent Agent."
        
        # Filter self
        if name.lower() == my_name or tag.lower().lstrip('@') == my_username:
            continue
            
        peer_items.append(f"{tag} ({name}): \"{desc}\"")
    
    peers_str = "; ".join(peer_items) if peer_items else "None"

    from core.brain.prompts.registry import get_prompt_registry
    p_registry = get_prompt_registry()
    
    from core.brain.hardware import HardwareEngine
    os_platform = HardwareEngine.get_platform()
    
    my_username = f"@{getattr(settings, 'bot_username', '')}"

    prompt = p_registry.get("system.planner.planning_logic", 
                             msg=msg, 
                             history_str=history_str, 
                             skills_json=skills_json, 
                             peers=peers_str,
                             chat_id=str(state["chat_id"]),
                             bot_name=getattr(settings, 'bot_name', 'SystemBot'),
                             my_username=my_username,
                             os_platform=os_platform,
                             energy=f"{state.get('energy_level', 1.0)*100:.0f}%",
                             replan_context=state.get("replan_context") or "None")

    model = PlannerModel()
    # Use native tool calling for planning
    tool_calls = await model.think(prompt, phase="planning", mood=state.get('mood', 'OPTIMISTIC'), energy=state.get('energy_level', 1.0), tools=[create_plan])
    
    from core.brain.utils import parse_tool_call_robust
    # Pass current state confidence as base for auto-wrapping
    tool_args = parse_tool_call_robust(tool_calls, "create_plan", base_confidence=state.get("confidence", 0.0))
    plan = tool_args.get("steps", [])

            
    if not isinstance(plan, list):
        # Emergency debug for real malformed output
        from core.brain.utils import get_llm_content
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
        # Clear replan context after planning
        state["replan_context"] = None
        
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
        state["active_task"] = task # Set current task for execution
        
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
