from ..state import ChatState
import re
from core.identity import AgentIdentity
from config.settings import settings
from utils.logger import get_logger
from langchain_ollama import ChatOllama

logger = get_logger()

from ..model import SharedModelProvider, BrainModel
from langchain_core.tools import tool

@tool
def route_intent(decision: str, intent: str, rationale: str = None) -> str:
    """Classify the user message into a decision tier and provide intent details.
    
    Args:
        decision: The high-level routing decision. Must be one of:
            - CHAT: Simple conversation, identity questions, or social interaction.
            - PLAN: Tasks requiring data access, tools, calculations, multi-step coordination, or external research.
            - NONE: The message is not addressed to you or is irrelevant.
        intent: A descriptive name for the detected specific intent (e.g., 'CheckWeather', 'QueryUserCount').
        rationale: Brief internal reasoning for this decision.
    """
    pass

# Identity wrapper for thinking
class RouterModel(BrainModel):
    def __init__(self):
        super().__init__(mode="routing")

    async def think(self, prompt: str, phase: str = "routing", mood: str = "OPTIMISTIC", energy: float = 1.0, tools: list = None) -> str:
        # NGO: Add custom debug logging for Router
        import time
        t_start = time.time()
        logger.debug(f"[ROUTER_DEBUG] Sending prompt to LLM (Prompt Length: {len(prompt)} chars)...")
        
        # Use parent think method (increased timeout for routing)
        try:
            response = await super().think(prompt, phase=phase, mood=mood, energy=energy, timeout=600.0, tools=tools)
            t_end = time.time()
            logger.debug(f"[ROUTER_DEBUG] LLM Response received in {t_end - t_start:.2f}s")
            return response
        except Exception as e:
            logger.error(f"[ROUTER_DEBUG] LLM thinking failed: {e}")
            raise

async def chat_route_node(state: ChatState) -> ChatState:
    """
    NEURAL ROUTER: Determine if the request needs a multi-step plan.
    Enhanced with Phase 14.0 PPF + Phase 15.2 ACR Integration + Feedback Bus.
    """
    # NGO FIX: Prevent double routing when resuming graph in background
    if (state.get("plan") or state.get("phase") in ["routed", "planned"]) and state.get("needs_planning") is not None:
        logger.info(f"[ROUTER] Skipping routing (Already {state.get('phase', 'with plan')}).")
        return state

    msg = state["user_message"]
    
    # --- PHASE 1 & 4: DIGITAL ENTITY - EMOTION & CIRCADIAN ---
    try:
        from utils.emotion import compute_digital_entity_state
        state_memory = state.get("context", {}).get("memory")
        chat_id = state.get("chat_id")
        
        vibe_score = 0.5
        if state_memory and chat_id:
            stored_vibe = await state_memory.recall(f"affinity_score:{chat_id}")
            if stored_vibe is not None:
                vibe_score = float(stored_vibe)
                
        # Compute mood and energy
        entity_state = compute_digital_entity_state(affinity_score=vibe_score)
        state["mood"] = entity_state["mood"]
        state["energy_level"] = entity_state["energy_level"]
        state["user_affinity"] = entity_state["user_affinity"]
        logger.debug(f"[ROUTER] Digital Entity State - Affinity: {vibe_score:.2f}, Energy: {state['energy_level']}")
    except Exception as e:
        logger.warning(f"[ROUTER] Failed to compute emotion/circadian state: {e}")
    
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
    # Fetch registered bots from mailbox to improve name resolution for ALL messages
    peer_bot_map = {}
    known_peers = []
    try:
        from skills.mcp_realm import get_mcp_realm
        mcp = get_mcp_realm()
        peer_bot_map = await mcp.get_bot_registrations()
        if peer_bot_map:
            for name, tag in peer_bot_map.items():
                known_peers.append(name.lower())
                known_peers.append(tag.lower().lstrip('@'))
    except Exception as e:
        logger.debug(f"[ROUTER] Failed to fetch peer registrations: {e}")

    is_bus_a2a = bool(a2a_match)
    sender_bot = a2a_match.group(1) if a2a_match else None
    
    # --- NGO ENHANCEMENT: Peer-to-Peer detection in Group Chat ---
    msg_no_bus_tag = msg # msg without the A2A_BUS tag
    if is_bus_a2a:
        msg_no_bus_tag = msg.replace(a2a_match.group(0), "").strip()

    # --- NGO HARD PRE-FILTER (v2): Multi-bot intent check with boundary boundary ---
    if not is_bus_a2a:
        msg_clean = msg_no_bus_tag.strip()
        
        import re as _re
        
        # 1. Am I being addressed at the start?
        i_am_target = False
        self_identifiers = [my_username, my_name]
        for s in self_identifiers:
            if not s or len(s) < 3: continue
            s_clean = s.lower().lstrip('@')
            # Match start of string, optional @, followed by name and a word boundary or punctuation
            pattern = _re.compile(rf'^@?{_re.escape(s_clean)}(?![a-zA-Z0-9_\-])', _re.IGNORECASE)
            if pattern.match(msg_clean):
                i_am_target = True
                break
        
        # 2. Am I mentioned ANYWHERE in the message? (OpenClaw Mention Gate)
        i_am_mentioned_anywhere = False
        for s in self_identifiers:
            if not s or len(s) < 3: continue
            s_clean = s.lower().lstrip('@')
            # Match anywhere, preceded by non-word char or start of string
            pattern = _re.compile(rf'(?:^|[^a-zA-Z0-9_])@?{_re.escape(s_clean)}(?![a-zA-Z0-9_\-])', _re.IGNORECASE)
            if pattern.search(msg_clean):
                i_am_mentioned_anywhere = True
                break

        # 3. If I'm not the target, is someone else?
        message_starts_with_any_peer = False
        if not i_am_target:
            for p in set(known_peers):
                if not p or len(p) < 4: continue
                p_clean = p.lower().lstrip('@')
                pattern = _re.compile(rf'^@?{_re.escape(p_clean)}(?![a-zA-Z0-9_\-])', _re.IGNORECASE)
                if pattern.match(msg_clean):
                    message_starts_with_any_peer = True
                    break
        
        # 4. Decision: OpenClaw-inspired Routing Gate
        # We NO LONGER hardcode grammatical checks like "và", "cả hai" (Group Intent).
        # We rely on the Mention Gate: If we are mentioned ANYWHERE, we let it pass to LLM.
        # If the message is explicitly targeted at someone else and we are NOT mentioned anywhere, drop it.
        if message_starts_with_any_peer and not i_am_target and not i_am_mentioned_anywhere:
            logger.info(f"[ROUTER] 🛑 NGO Pre-Filter: Message addresses another peer & bot not mentioned ({msg_clean[:20]}...). Silent mode.")
            state["phase"] = "routed"
            state["decision"] = "NONE"
            from ..algorithms.feedback_bus import get_feedback_bus
            get_feedback_bus().emit("ROUTING_OUTCOME", {"decision": "NONE", "method": "HARD_PREFILTER_PEER_V2"}, source="router")
            return state
            
    # ========================================
    # PHASE 14.0 + 15.2: PPF → ACR → Feedback Bus
    # Connected pipeline: PPF predicts → ACR fuses signals → Bus records
    # ========================================
    from ..algorithms.ppf_classifier import get_ppf_classifier, PPFClassifier
    from ..algorithms.confidence_engine import get_confidence_engine
    from ..algorithms.feedback_bus import get_feedback_bus
    
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
    
    if tier == "auto" and conf > 0.92 and ppf_decision:
        # HIGH CONFIDENCE: Brain routes instinctively (no LLM needed)
        logger.info(f"[ROUTER] ⚡ Instinctive route: {ppf_decision} (confidence: {conf:.2f}) — no LLM needed")
        _apply_routing_decision(state, ppf_decision, msg)
        
        from ..algorithms.feedback_bus import get_feedback_bus
        bus = get_feedback_bus()
        
        state["thoughts"].append(f"Router: Instinctive decision `{ppf_decision}` (conf={conf:.2f}). No deliberation needed.")
        ppf.record(ppf_features, ppf_decision)
        acr.record_query(msg, ppf_decision)
        bus.emit("ROUTING_OUTCOME", {
            "decision": ppf_decision, "method": "INSTINCT_AUTO",
            "ppf_bypassed": True, "confidence": conf,
        }, source="router")
        state["phase"] = "routed"
        state["_ppf_features"] = ppf_features.tolist()
        return state
    
    # BRIEF or FULL TIER: Need LLM assistance
    import json
    from skills.registry import get_skill_registry
    registry = get_skill_registry()
    active_tools = await registry.get_tool_schemas()
    skills_compact = "\n".join([f"- {s['name']}: {s['description']}" for s in active_tools])

    from ..prompts.registry import get_prompt_registry
    p_registry = get_prompt_registry()
    
    # Contextual awareness: Optimized history (Summary + Recent) via ContextManager
    from memory.context import ConversationContextManager
    ctx_manager = ConversationContextManager(char_limit_per_message=500, total_history_limit=2000)
    history_str = await ctx_manager.get_optimized_history(state["chat_id"], state["context"]["memory"], limit=5)
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

    peers_list = ", ".join([f"@{tag.lstrip('@')} ({name})" for name, tag in peer_bot_map.items()]) if peer_bot_map else "None"
    
    dynamic_examples = await registry.get_routing_examples()
    
    # === BRIEF TIER: Compressed scaffold (~400 tokens vs ~2000) ===
    # When confidence is moderate (0.50-0.80), use minimal prompt — brain
    # already has a good guess, just needs LLM confirmation.
    if tier == "brief" and ppf_decision:
        brief_scaffold = f"""Classify intent. CHAT=conversation only. PLAN=needs tools/data/action. NONE=not for me.
You are {getattr(settings, 'bot_name', 'Brain')} (@{getattr(settings, 'bot_username', 'bot')}).
Co-workers in this chat: {peers_list}
Intuition: {intuition_signal}
Hint prediction: {ppf_decision} {hint}
Context: {first_message}
Tools: {skills_compact[:300]}

REQUEST: "{msg}"

Select ONE decision from [CHAT, PLAN, NONE] by calling the `route_intent` tool.
Do not provide any text output outside of the tool call."""
        
        logger.info(f"[ROUTER] 📋 Brief tier — compressed scaffold ({len(brief_scaffold)} chars)")
        model = RouterModel()
        prompt = brief_scaffold
    else:
        # === FULL TIER: Complete YAML prompt for complex/novel queries ===
        prompt = p_registry.get("system.router.routing_logic", 
                              msg=msg, 
                              history_str=history_str,
                              skills_compact=skills_compact,
                              hint=hint,
                              intuition=intuition_signal,
                              peers=peers_list,
                              dynamic_examples=dynamic_examples,
                              bot_name=getattr(settings, 'bot_name', 'Brain'),
                              bot_username=getattr(settings, 'bot_username', 'bot'),
                              user_pronoun=getattr(settings, 'user_pronoun', 'Sếp'),
                              bot_pronoun=getattr(settings, 'bot_pronoun', 'em'),
                              mood=state.get('mood', 'OPTIMISTIC'), 
                              energy=f"{state.get('energy_level', 1.0)*100:.0f}%")
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
        state["is_fast_track"] = True


