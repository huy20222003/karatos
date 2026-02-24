from ..state import ChatState
from core.identity import AgentIdentity
from utils.logger import get_logger
import asyncio, textwrap

logger = get_logger()

from ..model import SharedModelProvider, BrainModel

class SelfCorrectionModel(BrainModel):
    def __init__(self):
        super().__init__(mode="brief")

    async def evaluate(self, user_msg: str, response: str, mood: str, energy: float) -> str:
        """Evaluate and potentially correct a response"""
        from ..prompts.registry import get_prompt_registry
        registry = get_prompt_registry()
        
        from config.settings import settings
        bot_name = getattr(settings, 'bot_name', 'Brain')
        peer_bot_map = getattr(settings, 'peer_bots', {})
        peers_list = ", ".join([f"@{tag} ({name})" for name, tag in peer_bot_map.items()]) if peer_bot_map else "None"

        prompt = registry.get(
            "persona.generator.self_correction",
            user_msg=user_msg,
            response=response,
            mood=mood,
            peers=peers_list,
            bot_name=bot_name,
            energy=f"{energy*100:.0f}%"
        )
        
        # Use parent think method
        return await super().think(prompt, phase="brief", mood=mood, energy=energy)

async def chat_self_correction_node(state: ChatState) -> ChatState:
    """
    SELF-CORRECTION: Validate the draft response and fix tone/errors.
    Enhanced with Phase 14.2 CIE (Cascade Intelligence Engine).
    """
    # --- NGO OPTIMIZATION: Short-Circuit Logic ---
    if state.get("is_fast_track"):
        logger.info("[NGO] Skipping self-correction for Fast-Track path.")
        return state
        
    # Skip for data-heavy queries to save time (Fidelity already enforced by strict synth prompt)
    task_outputs = state.get("task_outputs", [])
    has_valid_data = False
    for res in task_outputs:
        if isinstance(res, dict) and res.get("status") == "success" and res.get("data"):
            has_valid_data = True
            break
            
    if has_valid_data:
        logger.info("[NGO] Skipping self-correction for successful Data Realm results to preserve fidelity.")
        return state
    # ---------------------------------------------

    draft = state.get("response")
    if not draft or not isinstance(draft, str):
        return state
        
    logger.thought(f"{getattr(state['context'].get('identity'), 'name', 'Brain')} is double-checking her response...")
    
    # --- PHASE 14.2 + 15.4: CIE — Cascade Intelligence Engine ---
    from ..algorithms.cascade_evaluator import get_cascade_evaluator
    from ..algorithms.feedback_bus import get_feedback_bus
    
    cascade = get_cascade_evaluator()
    bus = get_feedback_bus()
    
    result = await cascade.evaluate(
        user_message=state["user_message"],
        response=draft,
        query_vector=state.get("query_vector"),
        response_vector=state.get("response_vector"),  # Phase 15.4: Now real!
        mood=state.get("mood", "OPTIMISTIC"),
        energy=state.get("energy_level", 1.0),
    )
    
    if result["corrections"]:
        logger.info(f"[CIE] Response corrected at Tier {result['tier_exited']}. Reason: {result['reason']}")
        
        state["response"] = result["corrections"]
        state["thoughts"].append(f"Self-Correction (CIE Tier {result['tier_exited']}): {result['reason']}")
        
        # Phase 15.3: Emit correction signal for metacognition
        bus.emit("CORRECTION", {
            "was_corrected": True,
            "tier": result["tier_exited"],
            "reason": result["reason"],
        }, source="self_correction")
    else:
        logger.info(f"[CIE] Response approved at Tier {result['tier_exited']}. No corrections needed.")
        bus.emit("CORRECTION", {
            "was_corrected": False,
            "tier": result["tier_exited"],
        }, source="self_correction")
    # ---------------------------------------------------
        
    return state

