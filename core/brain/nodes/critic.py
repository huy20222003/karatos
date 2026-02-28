import json
import asyncio
import textwrap
from typing import Dict, Any

from core.brain.state import AgentState
from core.brain.utils import extract_json
from core.identity import AgentIdentity
from utils.logger import get_logger
from core.brain.model import SharedModelProvider, BrainModel

logger = get_logger()

class CriticModel(BrainModel):
    def __init__(self):
        super().__init__(mode="brief")

    async def criticize(self, prompt: str, mood: str = "OPTIMISTIC", energy: float = 1.0) -> str:
        # Use parent think method
        return await super().think(prompt, phase="brief", mood=mood, energy=energy)

async def critic_node(state: AgentState) -> AgentState:
    """
    Review the active task before it is executed.
    This node acts as a safety guard to prevent false positives.
    """
    decision = state.get("active_task")
    if not isinstance(decision, dict):
        # Handle cases where task might be a list or None
        if isinstance(decision, list) and decision:
            decision = decision[0]
        else:
            logger.info("[CRITIC] No valid dictionary task found for review.")
            state["phase"] = "critic_skipped"
            return state

    # ROBUST KEY EXTRACTION
    proposed_action = decision.get("action", decision.get("task", decision.get("skill", "IGNORE")))
    
    if proposed_action == "IGNORE":
        logger.info("[CRITIC] Skipping review for IGNORE decision.")
        state["phase"] = "critic_skipped"
        return state

    target = state.get("current_target", {})
    evidence = state.get("evidence", [])
    
    # Summarize evidence for the critic
    # NGO: Look in state and context for ChatState compatibility
    user_msg = state.get("user_message") or state.get("context", {}).get("user_message")
    
    if not user_msg:
        # Fallback to planning thought or a generic indicator of autonomy
        user_msg = state.get("planning_thought") or "Autonomous system action"
        
    evidence_summary = f"USER REQUEST: {user_msg}" 
    if evidence:
        last_evidence = evidence[-1]
        reasoning = last_evidence.get("reasoning", "")
        risk_factors = ", ".join(last_evidence.get("risk_factors", []))
        evidence_summary += f" | Internal Context: [Reasoning: {reasoning}] [Risk Factors: {risk_factors}]"

    target_id = decision.get("target_id") or state.get("chat_id") or state.get("context", {}).get("chat_id") or "SYSTEM"
    target_type = decision.get("target_type", "USER" if (state.get("chat_id") or state.get("context", {}).get("chat_id")) else "SYSTEM")

    # NGO: Reverted hardcoded confidence. The brain should provide this via the planner.
    # Phase 21.1: Use state-level confidence if step-level is missing
    confidence = decision.get("confidence")
    if confidence is None:
        confidence = state.get("confidence", 0)
        logger.debug(f"[CRITIC] Using state-level confidence fallback: {confidence}")
    
    logger.thought(f"Internal Critic is reviewing decision: {proposed_action} on {target_id} (Confidence: {confidence})...")


    from core.brain.prompts.registry import get_prompt_registry
    registry = get_prompt_registry()
    
    # NGO: Use identity from state context (pre-loaded with memory)
    identity = state.get("context", {}).get("identity")
    if not identity:
        from core.identity import AgentIdentity
        identity = AgentIdentity()
    
    # EXTRACTION: Get params or args for the critic to see
    params = decision.get("params", decision.get("args", {}))
    # If it's a raw SQL auto-wrap, the key might be in params['query']
    proposed_details = json.dumps(params, ensure_ascii=False) if params else "None provided"

    prompt = registry.get(
        "system.autonomous.critic",
        target_type=target_type,
        target_id=target_id,
        target_reason=decision.get("thought") or decision.get("reason") or "No explicit reason provided by planner.",
        evidence_summary=evidence_summary,
        proposed_action=proposed_action,
        proposed_details=proposed_details,
        confidence=int(confidence * 100) if isinstance(confidence, float) else confidence,
        mood=state.get('mood', 'OPTIMISTIC'),
        sovereignty_principles=identity.sovereignty_principles,
        self_protection_protocol=identity.self_protection_protocol,
        bot_name=identity.active_name or identity.name
    )
    
    model = CriticModel()
    criticism_raw = await model.criticize(prompt, mood=state.get('mood', 'OPTIMISTIC'), energy=state.get('energy_level', 1.0))
    
    # Parse the criticism
    criticism = extract_json(criticism_raw) or {}
    
    state["thoughts"].append(f"Critic: {criticism.get('critique', 'No critique provided.')}")
    
    suggested_action = criticism.get("suggested_action", "APPROVED").upper()
    
    # NGO: Only force override if Critic suggested PENDING (Safety first).
    # For IGNORE or ALERT, we trust the explicit 'override' flag.
    should_override = criticism.get("override") or suggested_action == "PENDING"
    
    if should_override and suggested_action != "APPROVED":
        logger.warning(f"[CRITIC] OVERRIDE: {proposed_action} -> {criticism.get('suggested_action')}")
        logger.warning(f"[CRITIC] Reason: {criticism.get('suggested_reason')}")
        
        # Apply the override
        state["active_task"] = {
            "realm": decision.get("realm", "SYSTEM"), # Preserve or default realm
            "action": suggested_action.lower(),
            "target_id": decision.get("target_id"),
            "target_type": decision.get("target_type"),
            "reason": criticism.get("suggested_reason", decision.get("reason")),
            "params": params, # CRITICAL: Preserve context for re-execution or approval
            "confidence": decision.get("confidence", 0),
            "criticized": True,
            "override": True,
            "original_action": proposed_action
        }
    else:
        logger.info("[CRITIC] Task approved.")
        state["active_task"]["criticized"] = True
        state["active_task"]["critic_approved"] = True

    state["phase"] = "critic_complete"
    return state
