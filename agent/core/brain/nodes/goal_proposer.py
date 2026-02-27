import json
from typing import List
from ..state import AgentState
from ..utils import extract_json
from core.identity import AgentIdentity
from utils.logger import get_logger
from ..model import SharedModelProvider

logger = get_logger()

async def propose_goals_node(state: AgentState) -> AgentState:
    """
    PROPOSE_GOALS: Autonomously generate new objectives based on reflections.
    """
    identity = AgentIdentity()
    identity.current_mood = state.get("mood", "OPTIMISTIC")
    identity.energy = state.get("energy_level", 1.0)
    
    logger.thought(f"{identity.name} is thinking about future goals... 💡")
    
    model = SharedModelProvider.get_model()
    
    from ..prompts.registry import get_prompt_registry
    registry = get_prompt_registry()
    
    # Context for goal proposal
    last_reflection = state["thoughts"][-1] if state["thoughts"] else "No recent reflections."
    
    # STRATEGIST UPGRADE: Fetch long-term learnings
    from memory.persistent import get_memory, MemoryCategory
    memory = get_memory()
    
    # 1. Get recent Learnings (Lessons learned)
    learnings = await memory.search(category=MemoryCategory.LEARNING, limit=5, min_importance=0.6)
    learning_str = "\n".join([f"- {m.value}" for m in learnings]) if learnings else "No strategic learnings yet."
    
    # 2. Get recent Decision outcomes (What worked/failed)
    decisions = await memory.search(category=MemoryCategory.DECISION, limit=3, min_importance=0.7)
    decision_str = "\n".join([f"- {d.value.get('action')} -> {d.value.get('outcome')}" for d in decisions]) if decisions else "No major decisions yet."

    # 3. Get active Goals (What we're already pursuing)
    existing_goals = await memory.search(category=MemoryCategory.GOAL, limit=5, min_importance=0.5)
    goal_str = "\n".join([f"- {g.value}" for g in existing_goals]) if existing_goals else "No active goals."

    # 4. Get Habits (Recurring patterns to consider)
    habits = await memory.search(category=MemoryCategory.HABIT, limit=3, min_importance=0.5)
    habit_str = "\n".join([f"- {h.value}" for h in habits]) if habits else "No behavioral patterns detected."

    # Combined context into reflection payload
    current_action = state.get("action_result", {})
    action_str = f"Action: {current_action.get('action')} - Success: {current_action.get('success')}\nResult: {str(current_action.get('result'))[:1000]}" if current_action else "No action executed this cycle."

    strategic_context = (
        f"Last Reflection: {last_reflection}\n\n"
        f"=== CURRENT CYCLE ACTION ===\n"
        f"{action_str}\n\n"
        f"=== STRATEGIC CONTEXT (HISTORY) ===\n"
        f"Recent Learnings:\n{learning_str}\n\n"
        f"Recent Key Decisions:\n{decision_str}\n\n"
        f"Active Goals (avoid duplicates):\n{goal_str}\n\n"
        f"Behavioral Patterns:\n{habit_str}"
    )
    
    # Build prompt
    prompt = registry.get(
        "system.autonomous.propose_goals",
        reflection=strategic_context,
        mood=identity.current_mood,
        energy=f"{identity.energy*100:.0f}%"
    )
    
    try:
        response = await model.ainvoke(prompt)
        content = response.content if hasattr(response, 'content') else str(response)
        goals_data = extract_json(content)
        
        if isinstance(goals_data, list):
            # STRICT FILTER: Remove any self-evolution/internal optimization goals before they enter the state
            filtered_goals = []
            for goal in goals_data:
                title = goal.get('title', '').upper()
                motivation = goal.get('motivation', '').upper()
                
                # Keywords that trigger restricted 'Internal Optimization' behavior
                restricted_keywords = ["EVOLVE", "OPTIMIZE", "REFACTOR", "CODE", "SOURCE", "INTERNAL", "SELF-", "TRANSCEND"]
                
                if any(k in title for k in restricted_keywords) or any(k in motivation for k in restricted_keywords):
                    logger.debug(f"[GOAL_STRATEGIST] Blocked restricted goal: {goal.get('title')}")
                    continue
                
                filtered_goals.append(goal)
                logger.info(f"🍀 New Goal Proposed: {goal.get('title', 'Untitled')}")

            state["goals"] = filtered_goals
            
            # Optional: Record to persistent memory
            if memory:
                for goal in filtered_goals:
                    await memory.remember(
                        key=f"goal:{goal.get('id', 'unknown')}:{identity.current_mood}",
                        value=goal,
                        category=MemoryCategory.GOAL,
                        importance=0.6,
                        expires_in_days=7
                    )
        else:
            logger.warning("Goal proposal did not return a valid list of goals.")
            state["goals"] = []
            
    except Exception as e:
        logger.error(f"Goal proposal failed: {e}")
        state["goals"] = []
        
    state["phase"] = "propose_goals_complete"
    return state
