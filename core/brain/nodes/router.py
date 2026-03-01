from core.brain.state import ChatState
import re
from core.identity import AgentIdentity
from config.settings import settings
from utils.logger import get_logger
from langchain_ollama import ChatOllama
from datetime import datetime

logger = get_logger()

from core.brain.model import SharedModelProvider, BrainModel
from langchain_core.tools import tool

@tool
def route_intent(decision: str, intent: str, rationale: str = None, confidence: float = 1.0) -> str:
    """Classify the user message into a decision tier and provide intent details.
    
    Args:
        decision: The high-level routing decision. Must be one of:
            - CHAT: Simple conversation, identity questions, or social interaction.
            - PLAN: Tasks requiring data access, tools, calculations, multi-step coordination, or external research.
            - NONE: The message is not addressed to you or is irrelevant.
        intent: A descriptive name for the detected specific intent (e.g., 'CheckWeather', 'QueryUserCount').
        rationale: Brief internal reasoning for this decision.
        confidence: Your certainty score for this decision (0.0 to 1.0).
    """
    pass


# Identity wrapper for thinking
class RouterModel(BrainModel):
    def __init__(self):
        super().__init__(mode="routing")

    async def think(self, prompt: str, phase: str = "routing", mood: str = "OPTIMISTIC", energy: float = 1.0, tools: list = None) -> str:
        # Use parent think method (increased timeout for routing)
        try:
            response = await super().think(prompt, phase=phase, mood=mood, energy=energy, timeout=600.0, tools=tools)
            return response
        except Exception as e:
            logger.error(f"[ROUTER_DEBUG] LLM thinking failed: {e}")
            raise

async def chat_route_node(state: ChatState) -> ChatState:
    """
    NEURAL ROUTER: Determine if the request needs a multi-step plan.
    Enhanced with Phase 14.0 PPF + Phase 15.2 ACR Integration + Feedback Bus.
    """
    msg = state["user_message"]
    # NGO: Preserve metadata-aware logic
    processed = state.get("processed")
    content_type = processed.content_type if processed else "unknown"
    
    if content_type == "social" and len(msg.split()) < 4:
        logger.info(f"[ROUTER] ⚡ Metadata Fast-Track: SOCIAL intent detected.")
        state["decision"] = "CHAT"
        state["phase"] = "routed"
        return state
    # NGO FIX: Prevent double routing when resuming graph in background
    if (state.get("plan") or state.get("phase") in ["routed", "planned"]) and state.get("needs_planning") is not None:
        logger.info(f"[ROUTER] Skipping routing (Already {state.get('phase', 'with plan')}).")
        return state

    
    # --- PHASE 1 & 4: DIGITAL ENTITY - EMOTION & CIRCADIAN (Phase 25) ---
    try:
        from core.identity import AgentIdentity
        from utils.sentiment import analyze_sentiment
        
        # Use cached identity from parallel_startup (eliminates duplicate load_from_memory)
        identity = state.get("context", {}).get("identity")
        if not identity:
            identity = AgentIdentity()
        state_memory = state.get("context", {}).get("memory")
        chat_id = state.get("chat_id")
        
        vibe_score = 0.5
        if state_memory and chat_id:
            stored_vibe = await state_memory.recall(f"affinity_score:{chat_id}")
            if stored_vibe is not None:
                vibe_score = float(stored_vibe)
        
        # Initialize identity with stored affinity
        identity.user_affinity = vibe_score
        
        # 1. Evolve mood based on current message sentiment
        sentiment_score = await analyze_sentiment(msg)
        identity.evolve_mood(stimulus="MESSAGE_RECEIVED", outcome="success", sentiment=sentiment_score)
        
        # 2. Sync results to state for persona nodes
        circadian = identity._get_circadian_state()
        state["mood"] = f"{identity.current_mood}. note: {circadian['circadian_mood']}"
        state["energy_level"] = round(identity.energy, 2)
        state["user_affinity"] = round(identity.user_affinity, 2)
        
        # 3. Persist updated affinity (CIE Tier 3)
        if state_memory and chat_id:
            await state_memory.remember(f"affinity_score:{chat_id}", identity.user_affinity, importance=0.1)
    except Exception as e:
        logger.warning(f"[ROUTER] Failed to compute embodiment state: {e}")
    
    # --- NGO UNIVERSAL FIX: Always strip own name/tag from the start ---
    my_username = (getattr(settings, 'bot_username', '') or '').lower()
    my_name = (getattr(settings, 'bot_name', '') or '').lower()
    
    orig_msg_pre_strip = msg
    # NGO: Stop stripping self-names to give the Brain full raw context for better intent classification.
    # The LLM will now see if it was mentioned at the start/middle/end itself.
    pass

    # --- A2A METADATA EXTRACTION ---
    # Detect internal bus tags like [A2A_BUS: Message from @sender]
    a2a_match = re.search(r'\s*\[A2A_BUS: Message from @?([\w_-]+)\]', msg)
    
    # --- A2A METADATA & PEER DISCOVERY (Universal) ---
    # Use cached peer bot map from parallel_startup (eliminates duplicate MCP call)
    peer_bot_map = state.get("context", {}).get("peer_bot_map", {})
    known_peers = []
    if peer_bot_map:
        for name, tag in peer_bot_map.items():
            known_peers.append(name.lower())
            known_peers.append(tag.lower().lstrip('@'))

    is_bus_a2a = bool(a2a_match)
    sender_bot = a2a_match.group(1) if a2a_match else None
    
    # --- NGO ENHANCEMENT: Peer-to-Peer detection in Group Chat ---
    msg_no_bus_tag = msg # msg without the A2A_BUS tag
    if is_bus_a2a:
        msg_no_bus_tag = msg.replace(a2a_match.group(0), "").strip()

    # --- MENTION DETECTION (Neural Transition) ---
    # We NO LONGER hard-block messages in groups using regex.
    # The Brain (Router) will decide 'NONE' or 'CHAT' based on context and mention style.
    # This allows for more flexible interactions like answering 
    # when referred to with pronouns or in ambiguous ways.
    pass
            
    # ========================================
    # PHASE 14.0 + 15.2: PPF → ACR → Feedback Bus
    # Connected pipeline: PPF predicts → ACR fuses signals → Bus records
    # ========================================
    from core.brain.algorithms.ppf_classifier import get_ppf_classifier, PPFClassifier
    from core.brain.algorithms.confidence_engine import get_confidence_engine
    from core.brain.algorithms.feedback_bus import get_feedback_bus
    
    ppf = get_ppf_classifier()
    acr = get_confidence_engine()
    bus = get_feedback_bus()
    
    # Step 1: PPF Feature Extraction & Prediction
    ppf_features = PPFClassifier.extract_features(msg, state.get("query_vector"))
    ppf_decision, ppf_confidence = ppf.predict(ppf_features)
    
    # Step 2: Semantic Intent Match (IntentRegistry removed in Phase 21)
    intent_match = None
    intent_similarity = 0.0
    
    # Step 3: ACR Multi-Signal Fusion
    acr_result = acr.compute_confidence(
        user_message=msg,
        query_vector=state.get("query_vector"),
        ppf_confidence=ppf_confidence,
        ppf_decision=ppf_decision,
        intent_match=intent_match,
        intent_similarity=intent_similarity,
    )
    
    # Step 4: Route — Prompt-Free Cognition (Phase A)
    # When the brain is VERY confident, route instinctively without LLM.
    # Like a human handling routine tasks without conscious deliberation.
    tier = acr_result["tier"]
    conf = acr_result.get("confidence", 0.0)
    
    # NGO: Always preserve ACR confidence as base
    state["confidence"] = conf
    
    # NGO: User requested that ALL decisions go through the Brain (LLM), regardless of confidence.
    # Disabling the Instinctive Auto-route bypass.
    # if tier == "auto" and conf > 0.92 and ppf_decision:
    #     ...
    pass
    
    # BRIEF or FULL TIER: Need LLM assistance
    import json
    from skills.registry import get_skill_registry
    registry = get_skill_registry()
    skills_compact = registry.get_enriched_capabilities()

    from core.brain.prompts.registry import get_prompt_registry
    p_registry = get_prompt_registry()
    
    # Contextual awareness: Optimized history (Summary + Recent) via ContextManager
    from memory.context import ConversationContextManager
    ctx_manager = ConversationContextManager(char_limit_per_message=1000, total_history_limit=3000)
    history_str = await ctx_manager.get_optimized_history(state["chat_id"], state["context"]["memory"], limit=settings.context_planning_limit)
    first_message = history_str.split('\n')[0] if history_str else ""
    
    # --- SPECULATIVE HINT ---
    spec_ctx = state.get("speculative_data_context", {})
    hint = ""
    if spec_ctx.get("intent_detected"):
        tables = spec_ctx.get("tables", [])
        hint = f"HINT: Data intent detected for tables: {tables}"

    # --- INTUITION (GUT FEELING) LAYER ---
    conf = acr_result.get("confidence", 0.0)
    signals = acr_result.get("signals", {})
    
    if conf > 0.85:
        intuition_signal = f"STRONG FAMILIARITY ({conf:.2f}). Routine request."
    elif conf > 0.60:
        intuition_signal = f"MODERATE FAMILIARITY ({conf:.2f}). Standard with some novelty."
    else:
        intuition_signal = f"COGNITIVE DISSONANCE ({conf:.2f}). Unfamiliar pattern."
    
    if signals.get("ppf", 0) < 0.3 and signals.get("history", 0) < 0.3:
        intuition_signal += " (Brand new interaction pattern)."

    # NGO ENHANCED: Built Entity-based Peers list with Descriptions
    peer_items = []
    for name, data in peer_bot_map.items():
        # name is the simple key, data is the metadata dict {"url": ..., "tag": ..., "description": ...}
        # Filter out self
        is_self = (name.lower() == my_name) or (data.get("tag", "").lower().lstrip('@') == (my_username or "").lstrip('@'))
        if is_self:
            continue
            
        tag = data.get("tag", f"@{name}")
        desc = data.get("description", "Independent Agent.")
        peer_items.append(f"{tag} ({name}): \"{desc}\"")
    
    peers_list = "; ".join(peer_items) if peer_items else "None"
    
    logger.info(f"[ROUTER] Identified Peer Entities: {peers_list}")
    
    dynamic_examples = await registry.get_routing_examples()
    
    # === BRIEF TIER: Compressed scaffold (~400 tokens vs ~2000) ===
    # When confidence is moderate (0.50-0.80), use minimal prompt — brain
    # already has a good guess, just needs LLM confirmation.
    from datetime import datetime
    current_time = datetime.now().strftime("%H:%M")
    if tier == "brief" and ppf_decision:
        brief_scaffold = p_registry.get("system.router.router_brief",
                                        bot_name=getattr(settings, 'bot_name', 'Brain'),
                                        bot_username=getattr(settings, 'bot_username', 'bot'),
                                        peers=peers_list,
                                        intuition=intuition_signal,
                                        ppf_decision=ppf_decision,
                                        hint=hint,
                                        first_message=first_message,
                                        skills_compact=skills_compact[:1000],  # Increased budget
                                        dynamic_examples=dynamic_examples,     # Added missing examples!
                                        msg=msg,
                                        current_time=current_time)
        
        logger.info(f"[ROUTER] 📋 Brief tier — centralized scaffold ({len(brief_scaffold)} chars)")
        model = RouterModel()
        prompt = brief_scaffold
    else:
        from datetime import datetime
        current_time = datetime.now().strftime("%H:%M")
        prompt = p_registry.get("system.router.routing_logic", 
                              msg=msg, 
                              history_str=history_str,
                              skills_compact=skills_compact,
                              hint=hint,
                              intuition=intuition_signal,
                              peers=peers_list,
                              dynamic_examples=dynamic_examples,
                              bot_name=identity.active_name or getattr(settings, 'bot_name', 'Brain'),
                              bot_username=getattr(settings, 'bot_username', 'bot'),
                              user_pronoun=identity.active_user_pronoun or getattr(settings, 'user_pronoun', 'Anh'),
                              bot_pronoun=identity.active_bot_pronoun or getattr(settings, 'bot_pronoun', 'em'),
                              mood=state.get('mood', 'OPTIMISTIC'), 
                              energy=f"{state.get('energy_level', 1.0)*100:.0f}%",
                              current_time=current_time)
        model = RouterModel()

    # Use native tool calling for routing
    tool_calls = await model.think(prompt, phase="routing", mood=state.get('mood', 'OPTIMISTIC'), energy=state.get('energy_level', 1.0), tools=[route_intent])
    
    if tool_calls in ["ERROR_TIMEOUT", "ERROR_FAILED"]:
        state["error"] = tool_calls
        state["needs_planning"] = False
        state["phase"] = "routed"
        bus.emit("ROUTING_OUTCOME", {"decision": "ERROR", "method": "LLM_FAILED"}, source="router")
        return state

    decision = "CHAT"
    res = {}
    
    if isinstance(tool_calls, list) and tool_calls:
        res = tool_calls[0].get("args", {})
        decision = res.get("decision", "CHAT")
    else:
        # Handle cases where LLM didn't call the tool but returned text
        content_str = str(tool_calls).upper()
        if "PLAN" in content_str:
            decision = "PLAN"
        elif "NONE" in content_str:
            decision = "NONE"
        else:
            decision = "CHAT"
    
    # NGO SAFETY OVERRIDE (Phase 26): Enforce Private Chat integrity using metadata.
    chat_type = state.get("context", {}).get("channel_metadata", {}).get("chat_type")
    if not chat_type and processed:
        chat_type = getattr(processed, "metadata", {}).get("chat_type")
    
    is_private_chat = (chat_type == "private")
    
    if is_private_chat and decision == "NONE":
        if msg.strip() or state.get("context", {}).get("vision_extracted"):
            logger.info("[ROUTER] 🛡️ Private Chat Constraint: Overriding NONE -> CHAT to maintain interaction.")
            decision = "CHAT"
            res["decision"] = "CHAT"
            res["rationale"] = "Private chat requirement: AI must respond to direct user messages."
    
    # Phase 21.3: Bayesian Fusion of Intuition (ACR) and Conscious Reasoning (LLM)
    llm_conf = res.get("confidence")
    conscious_signal = float(llm_conf) if llm_conf is not None else 0.85 # Standard signal strength for active decision
    
    # Recalculate fused confidence using the full metadata
    fused_result = acr.compute_confidence(
        user_message=msg,
        query_vector=state.get("query_vector"),
        ppf_confidence=ppf_confidence,
        ppf_decision=ppf_decision,
        intent_match=intent_match,
        intent_similarity=intent_similarity,
        conscious_signal=conscious_signal
    )
    
    state["confidence"] = fused_result["confidence"]

    # Brain 2.6: Initialize Escalation State
    state["initial_decision"] = decision
    state["final_decision"] = decision
    state["escalation_level"] = 0
    state["decision_history"] = [{
        "decision": decision,
        "reason": res.get("rationale", "Initial routing"),
        "at_node": "chat_route_node",
        "timestamp": datetime.now().isoformat()
    }]



    _apply_routing_decision(state, decision, msg, res)
    rationale = res.get("rationale", "No rationale provided")
    logger.info(f"[ROUTER] Rationale: {rationale}")
    
    state["thoughts"].append(f"Router: Conscious decision `{decision}` (Rationale: {rationale})")
    
    # Learning: Record this LLM decision for all algorithms
    ppf.record(ppf_features, decision)
    acr.record_query(msg, decision)
    bus.emit("ROUTING_OUTCOME", {
        "decision": decision, "method": "LLM_FULL" if tier == "full" else "LLM_BRIEF",
        "ppf_bypassed": False,
        "ppf_prediction": ppf_decision,
        "ppf_was_correct": ppf_decision == decision if ppf_decision else None,
    }, source="router")
    
    state["phase"] = "routed"
    state["_ppf_features"] = ppf_features.tolist()
    return state


def _apply_routing_decision(state: ChatState, decision: str, msg: str, res: dict = None):
    """Helper: Apply a routing decision to state."""
    if decision == "NONE":
        logger.info(f"[ROUTER] ⏸️ NONE — Message not for this bot. Staying silent.")
        state["needs_planning"] = False
        state["is_fast_track"] = False
        state["response"] = None  # Signal: no response
    elif decision == "PLAN":
        logger.info(f"[ROUTER] Routing to CONSCIOUS PLANNER for: {msg}")
        state["needs_planning"] = True
        state["is_fast_track"] = False
        state["plan"] = []
        state["task_outputs"] = []
    else:  # CHAT
        logger.info(f"[ROUTER] Routing to CHAT (Persona) for: {msg}")
        state["needs_planning"] = False
        state["is_fast_track"] = False # NGO: Disable auto-fast-track to preserve History Context


