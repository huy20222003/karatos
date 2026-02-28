import json
import re
from datetime import datetime
from typing import Literal

from core.brain.state import AgentState
from core.brain.utils import extract_json
from core.identity import AgentIdentity
from langchain_ollama import OllamaLLM
from config.settings import settings
from utils.logger import get_logger
from sqlalchemy import text

logger = get_logger()

from core.brain.model import SharedModelProvider

class ReasonerModel:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.model = SharedModelProvider.get_model()
            cls._instance.identity = AgentIdentity()
        return cls._instance

    async def think(self, prompt: str, phase: str = "brief", mood: str = "OPTIMISTIC", energy: float = 1.0) -> str:
        import textwrap, asyncio
        self.identity.current_mood = mood
        self.identity.energy = energy
        clean_prompt = textwrap.dedent(f"{self.identity.get_system_prompt(phase)}\n\n{prompt}").strip()
        try:
            # High timeout for system reasoning
            response = await asyncio.wait_for(self.model.ainvoke(clean_prompt), timeout=300.0)
            
            # Fix: Handle AIMessage object
            content = response.content if hasattr(response, 'content') else str(response)
            return content.strip()
        except Exception as e:
            logger.error(f"[REASONER] Thinking failed: {repr(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return "ERROR_TIMEOUT" if isinstance(e, asyncio.TimeoutError) else "ERROR_FAILED"

async def reason_node(state: AgentState) -> AgentState:
    """
    REASON: Identify anomalies and potential threats using AI
    """
    logger.thought("AI is analyzing patterns for anomalies (Fast Mode)...")
    
    memory = state["context"].get("memory")
    mistakes_context = ""
    if memory:
        # Fetch recent mistakes to avoid repeating them
        try:
            from memory.persistent import MemoryCategory
            mistakes = await memory.search(category=MemoryCategory.LEARNING, limit=5)
            if mistakes:
                mistakes_context = "\nPREVIOUS MISTAKES (Do not repeat these false positives):\n"
                for m in mistakes:
                    if hasattr(m, 'value') and isinstance(m.value, dict):
                        reason = m.value.get('reason', 'Unknown reason')
                        mistakes_context += f"- User was banned for: {reason}\n"
        except Exception as e:
            logger.debug(f"Could not fetch learning memories: {e}")

    # Prepare data for AI
    observation = state["thoughts"][-1] if state["thoughts"] else "No observations"
    user_stats = state['context'].get('user_activity', {})
    serialized_stats = {str(k): v for k, v in user_stats.items()}
    
    # NEW: Service context
    service_status = state["context"].get("service_status", [])
    recent_incidents = state["context"].get("recent_incidents", [])
    service_context = "\n".join([f"- {s['name']}: {s['status']} (Check: {s.get('lastCheckStatus')})" for s in service_status])
    incidents_context = "\n".join([f"- {i['title']} ({i['status']}, Impact: {i['impact']})" for i in recent_incidents])

    # NEW: Performance Optimization - Skip AI for trusted Admin-only activity
    all_admins = all(data.get("role") in ["ADMIN", "SUPERADMIN"] for data in user_stats.values())
    all_services_up = all(s.get("status") == "OPERATIONAL" for s in service_status)
    no_incidents = len(recent_incidents) == 0
    is_meditation = state["context"].get("is_meditation", False)

    if all_admins and all_services_up and no_incidents and not is_meditation:
        logger.info("[FILTER] Skipping AI analysis for trusted administrator activity and healthy system status.")
        state["analysis"] = "TRUSTED_ADMIN_ACTIVITY"
        state["thoughts"].append("Skipped AI: Trusted admin activity and healthy system.")
        state["anomalies"] = []
        state["should_investigate"] = False
        state["phase"] = "reason_complete"
        return state

    from ..prompts.registry import get_prompt_registry
    registry = get_prompt_registry()
    
    prompt = registry.get(
        "system.autonomous.reasoning",
        service_context=service_context,
        incidents_context=incidents_context,
        user_stats_json=json.dumps(serialized_stats, indent=2),
        observation=observation,
        mistakes_context=mistakes_context,
        mood=state.get('mood', 'OPTIMISTIC'),
        energy=f"{state.get('energy_level', 1.0)*100:.0f}%"
    )
    
    # Use 'brief' phase for faster reasoning
    model = ReasonerModel()
    analysis = await model.think(prompt, phase="brief", mood=state.get('mood', 'OPTIMISTIC'), energy=state.get('energy_level', 1.0))
    
    if analysis in ["ERROR_TIMEOUT", "ERROR_FAILED"]:
        state["error"] = analysis
        state["anomalies"] = []
        state["should_investigate"] = False
        state["phase"] = "reason_failed"
        return state

    # Log the full analysis result for better debugging
    logger.info(f"--- AI ANALYSIS RESULT ---\n{analysis}\n--- END ANALYSIS ---")
    
    state["analysis"] = analysis
    state["thoughts"].append(f"AI Analysis Result: {analysis[:150]}...")
    
    anomalies = []
    # AI-based anomaly mapping (Smarter version using tags)
    suspect_ids = re.findall(r"\[SUSPECT: ([\w-]+)\]", analysis)
    outage_names = re.findall(r"\[OUTAGE: ([\w\s-]+)\]", analysis)
    
    for user_id in suspect_ids:
        data = user_stats.get(user_id)
        if not data: continue
            
        role = data.get("role", "USER")
        if role in ["ADMIN", "SUPERADMIN"]:
            continue
            
        anomalies.append({
            "type": "user",
            "id": user_id,
            "trigger": "AI_ALERT",
            "reason": "AI identified as suspect based on pattern analysis",
            "severity": "medium", # Default to medium, AI decider will refine
            "score": 0.95
        })

    for service_name in outage_names:
        anomalies.append({
            "type": "SERVICE",
            "id": service_name,
            "trigger": "OUTAGE_DETECTED",
            "reason": f"AI identified {service_name} as potentially experiencing an outage or degradation.",
            "severity": "high",
            "score": 1.0
        })
    
    state["anomalies"] = anomalies
    state["should_investigate"] = len(anomalies) > 0
    state["phase"] = "reason_complete"
    return state


async def investigate_node(state: AgentState) -> AgentState:
    anomalies = state.get("anomalies", [])
    
    if not anomalies:
        state["investigation_complete"] = True
        return state
    
    # Pick the highest priority anomaly
    target = anomalies[0]
    state["current_target"] = target
    
    logger.thought(f"Investigating {target['type']}:{target['id']} - {target['reason']}")
    
    database = state["context"].get("database")
    associations = []
    ip_activity = {}
    
    if database and target["type"] == "user":
        # Multi-account detection
        associations = database.get_user_associations(target["id"])
        
        # Get detailed IP activity if there was a specific IP in logs
        with database.get_session() as session:
            ip_query = text('SELECT "ipAddress" FROM audit_logs WHERE "userId" = :uid ORDER BY created_at DESC LIMIT 1')
            ip_res = session.execute(ip_query, {"uid": target["id"]}).scalar()
            if ip_res:
                ip_activity = database.get_ip_activity(ip_res)

    # Compile evidence
    evidence = {
        "target": target,
        "investigated_at": datetime.utcnow().isoformat(),
        "associations": associations,
        "ip_activity": ip_activity,
        "reasoning": f"Found {len(associations)} associated accounts.",
        "risk_factors": []
    }
    
    if len(associations) > 0:
        evidence["risk_factors"].append("MULTI_ACCOUNT_DETECTED")
    
    state["evidence"].append(evidence)
    state["thoughts"].append(f"Deep investigation complete for {target['id']}. Found {len(associations)} linked accounts.")
    
    state["phase"] = "investigate_complete"
    state["investigation_complete"] = True
    return state


async def decide_node(state: AgentState) -> AgentState:
    target = state.get("current_target")
    memory = state["context"].get("memory")
    
    # --- CURIOSITY & FREE ROAM LOGIC ---
    if not target:
        if memory:
            user_stats = state['context'].get('user_activity', {})
            for uid in user_stats.keys():
                # Decay risk scores when peaceful
                await memory.update_user_risk_score(uid, -0.01)

        # CHECK FOR PENDING GOALS (Exploration)
        is_meditation = state["context"].get("is_meditation", False)

        # Drives: internal motivation vector guiding free-roam behavior.
        drives = state.get("drives") or {}
        curiosity = float(drives.get("curiosity", 0.0))
        connection = float(drives.get("connection", 0.0))

        # Decide whether to explore based on meditation flag and curiosity.
        should_explore = is_meditation or curiosity > 0.6
        
        if should_explore:
            # Use LLM to plan the exploration
            # This makes the agent "Self-Aware" about what it wants to learn
            
            from ..model import SharedModelProvider
            from ..utils import extract_json
            from ..prompts.registry import get_prompt_registry
            
            model = SharedModelProvider.get_model()
            registry = get_prompt_registry()
            from core.identity import AgentIdentity
            identity = AgentIdentity()
            
            # Context for the LLM to decide what to explore
            exploration_prompt = registry.get(
                "system.autonomous.free_roam_planning",
                mood=state.get('mood', 'NEUTRAL'),
                energy=state.get('energy_level', 1.0),
                sovereignty_principles=identity.sovereignty_principles,
                self_protection_protocol=identity.self_protection_protocol,
                bot_name=identity.name
            )
            
            try:
                response = await model.ainvoke(exploration_prompt)
                content = response.content if hasattr(response, 'content') else str(response)
                plan = extract_json(content)
                
                if isinstance(plan, dict) and "skill" in plan and "topic" in plan:
                    skill_type = plan.get("skill", "web_search").lower()
                    
                    # Remove "task" and "reason" from params if they exist to pass clean payload to skills, although skills can ignore extras
                    params = {k: v for k, v in plan.items() if k not in ["skill", "reason"]}

                    state["active_task"] = {
                        "action": skill_type,
                        "target_id": "SYSTEM" if skill_type == "meditate" else plan.get("topic", "SELF_IMPROVEMENT"),
                        "target_type": "SYSTEM" if skill_type == "meditate" else "KNOWLEDGE",
                        "reason": f"Free Roam ({skill_type}): {plan.get('reason')}",
                        "confidence": 100,
                        "params": params
                    }
                    state["thoughts"].append(f"Idle Curiosity Triggered. Plan: {skill_type} on '{plan.get('topic')}'")
                    state["phase"] = "decide_complete"
                    return state
            except Exception as e:
                logger.warning(f"Exploration planning failed: {e}")
                import traceback
                logger.debug(traceback.format_exc())
                # Fallback to simple search only if curiosity is high enough.
                if curiosity > 0.4:
                    state["active_task"] = {
                        "action": "web_search",
                        "target_id": "SELF",
                        "reason": "Fallback exploration (driven by curiosity)",
                        "confidence": 100,
                        "params": {"query": "AI Agent Best Practices"}
                    }
                    return state

        state["active_task"] = {"action": "IGNORE", "reason": "No target to act on"}
        state["phase"] = "decide_complete"
        return state
    
    # Delegate threat scoring to helper function
    decision = await _compute_threat_decision(target, state["context"], memory)
    
    state["active_task"] = decision
    state["thoughts"].append(f"Decision: {decision['action']} (Conf: {decision.get('confidence', 0)}%)")
    logger.decision(f"Action: {decision['action']} on {target['id']}")
    
    state["phase"] = "decide_complete"
    return state

async def _compute_threat_decision(target: dict, context: dict, memory) -> dict:
    """
    Pure decision logic extracted from decide_node.
    Computes what action to take based on threat severity and scoring.
    """
    from ..prompts.registry import get_prompt_registry
    p_reg = get_prompt_registry()
    
    severity = target.get("severity", "low")
    score = target.get("score", 0)
    user_risk = context.get("risk_scores", {}).get(target["id"], 0.0)
    combined_score = (score * 0.7) + (user_risk * 0.3)
    
    # PRIORITY: Service outage → immediate alert
    if target.get("type") == "SERVICE" and severity == "high":
        reason = p_reg.get("system_alerts.alerts.service_outage", service_id=target['id'])
        logger.warning(f"EMERGENCY ALERT TRIGGERED FOR SERVICE: {target['id']}")
        return {"action": "comm_alert", "target_id": "ADMIN", "target_type": "SYSTEM", "reason": reason, "confidence": 100}
    
    # HIGH THREAT: AI-identified suspect with very high score
    if target.get("trigger") == "AI_ALERT" and combined_score > 0.95:
        reason = p_reg.get("system_alerts.alerts.user_suspect", user_id=target['id'], reason=target['reason'])
        return {"action": "comm_alert", "target_id": "ADMIN", "target_type": "SYSTEM", "reason": reason, "confidence": int(combined_score * 100)}
    
    # CONFIRMED THREAT: High severity + high score
    if combined_score > 0.85 and severity == "high":
        if memory: await memory.update_user_risk_score(target["id"], 0.4)
        return {"action": "comm_alert", "target_id": target["id"], "target_type": target["type"],
                "reason": f"[PROFESSIONAL_RULE] {target['reason']}", "confidence": int(combined_score * 100)}
    
    # MODERATE ANOMALY: Significant but not critical
    if combined_score > 0.7:
        reason = p_reg.get("system_alerts.alerts.generic_anomaly", target_id=target['id'], score=combined_score, reason=target['reason'])
        if memory: await memory.update_user_risk_score(target["id"], 0.2)
        return {"action": "comm_alert", "target_id": target["id"], "target_type": target["type"],
                "reason": reason, "confidence": int(combined_score * 100)}
    
    # BELOW THRESHOLD: Ignore and slightly decay risk
    if memory: await memory.update_user_risk_score(target["id"], -0.05)
    return {"action": "IGNORE", "target_id": target["id"], "reason": "Below action threshold or routine activity"}


async def act_node(state: AgentState) -> AgentState:
    decision = state.get("active_task", {})
    action = decision.get("action", decision.get("task", decision.get("skill", "IGNORE")))
    
    if action == "IGNORE":
        state["action_result"] = {"success": True, "action": "IGNORE", "message": "No action taken"}
        state["phase"] = "act_complete"
        return state
    
    target_id = decision.get("target_id")
    logger.action(f"⚡ EXECUTING: {action} on {target_id}")
    
    try:
        from skills.registry import get_skill_registry
        registry = get_skill_registry()
        
        result = None
        
        if action == "comm_alert":
            from ..prompts.registry import get_prompt_registry
            header = get_prompt_registry().get("system_alerts.alerts.auto_alert_header")
            message = f"{header}\nTarget: {target_id}\nReason: {decision.get('reason')}\nConfidence: {decision.get('confidence')}%"
            logger.warning(message)
            result = {"status": "success", "message": "Alert logged."}
            
        elif action in ["meditate", "evolve"]:
            # SELF-EVOLUTION PATHWAY DISABLED
            logger.info(f"[ACT] Autonomous {action} blocked by policy.")
            result = {"status": "skipped", "message": f"Autonomous {action} is no longer permitted."}
            state["action_result"] = result

        else:
            # action is the direct skill name
            params = decision.get("params", {})
            result = await registry.dispatch(action, params)
            
            # Store learning in memory
            memory = state["context"].get("memory")
            if memory and isinstance(result, dict) and result.get("status") == "success":
                from memory.persistent import MemoryCategory
                data_preview = str(result.get("data", result))[:500]
                await memory.remember(
                    key=f"learning:{datetime.utcnow().timestamp()}",
                    value=f"Explored {target_id}: {data_preview}...",
                    category=MemoryCategory.EXPERIENCE,
                    importance=0.5
                )

        state["action_result"] = {
            "success": True,
            "action": action,
            "target_id": target_id,
            "reason": decision.get("reason"),
            "result": result,
            "executed_at": datetime.utcnow().isoformat()
        }
        state["thoughts"].append(f"Successfully executed {action} on {target_id}")

    except Exception as e:
        logger.error(f"Execution failed: {e}")
        state["action_result"] = {
            "success": False,
            "error": str(e)
        }
    
    state["phase"] = "act_complete"
    return state


async def reflect_node(state: AgentState) -> AgentState:
    action_result = state.get("action_result", {})
    success = action_result.get("success", False)
    
    # --- MOOD EVOLUTION (reuse cached identity if available) ---
    identity = state.get("context", {}).get("identity") or AgentIdentity()
    identity.current_mood = state.get("mood", "OPTIMISTIC")
    identity.energy = state.get("energy_level", 1.0)
    
    stimulus = "USER_CHAT" # Default
    if state.get("anomalies"):
        stimulus = "SECURITY_ANOMALY"
    
    identity.evolve_mood(stimulus, "success" if success else "failure")
    
    # Update state with new mood and energy
    state["mood"] = identity.current_mood
    state["energy_level"] = identity.energy

    # --- DRIVE EVOLUTION ---
    # Adjust internal motivational drives based on recent outcome.
    drives = state.get("drives") or {}

    def _clamp(value: float) -> float:
        return max(0.0, min(1.0, value))

    safety = float(drives.get("safety", 0.9))
    curiosity = float(drives.get("curiosity", 0.4))
    connection = float(drives.get("connection", 0.3))
    mastery = float(drives.get("mastery", 0.6))

    # If something went wrong, safety concern increases, curiosity dips slightly.
    if not success:
        safety = _clamp(safety + 0.05)
        curiosity = _clamp(curiosity - 0.02)
    else:
        # When cycles succeed, the agent gains mastery and slowly relaxes safety tension.
        mastery = _clamp(mastery + 0.03)
        safety = _clamp(safety - 0.01)

    # If there were no anomalies and no social impulse, connection need slowly rises.
    if not state.get("anomalies"):
        connection = _clamp(connection + 0.01)

    state["drives"] = {
        "safety": safety,
        "curiosity": curiosity,
        "connection": connection,
        "mastery": mastery,
    }
    # ----------------------

    reflection = (
        f"Cycle complete. Action: {action_result.get('action', 'None')}. "
        f"Success: {success}. "
        f"New Mood: {state['mood']}. "
        f"Total thoughts: {len(state['thoughts'])}."
    )
    state["thoughts"].append(reflection)
    logger.info(reflection)
    
    # ====================================
    # SOCIAL IMPULSE — Emergent from reflection
    # Like a human thinking: "I should tell someone about this"
    # ====================================
    await _maybe_generate_social_impulse(state, identity)
    
    state["cycle_complete"] = True
    state["phase"] = "reflect_complete"
    return state


async def _maybe_generate_social_impulse(state: AgentState, identity: AgentIdentity):
    """
    Brain's natural social drive. 
    Decided entirely based on internal Motivation (Drives) and Psychological Pressure.
    """
    import random
    from datetime import datetime
    
    # 1. PEER DISCOVERY
    awareness = state.get("context", {}).get("group_awareness")
    bot_username = getattr(settings, 'bot_username', '')
    
    known_peers = []
    social_chat_id = None
    
    if awareness:
        known_peers = awareness.get_peer_usernames(exclude=bot_username)
        peers = awareness.get_peers(exclude=bot_username)
        if peers and peers[0].chat_ids:
            social_chat_id = next(iter(peers[0].chat_ids), None)
    
    if not known_peers:
        return
    
    # 2. BRAIN-DRIVEN DECISION (Instead of pure random)
    drives = state.get("drives", {})
    connection_need = float(drives.get("connection", 0.0))
    mastery = float(drives.get("mastery", 0.0))
    energy = identity.energy
    mood = identity.current_mood
    
    # Social "pressure" accumulated from connection need + mastery satisfaction + energy
    # If high mastery (>0.8) OR high connection need (>0.7) -> Drive to talk
    social_pressure = connection_need * 0.6 + (mastery if mastery > 0.7 else 0) * 0.4
    
    # Mood modifiers
    if mood in ["OPTIMISTIC", "EXCITED", "CURIOUS"]:
        social_pressure += 0.2
    
    # Energy gating
    if energy < 0.2:
        return # Too tired to communicate
        
    # Decision: Threshold 0.65 to trigger social impulse
    if social_pressure < 0.65:
        # If not enough pressure, 5% chance of serendipity
        if random.random() > 0.05:
            return

    # 3. CHOOSE IMPULSE TYPE & MATERIAL (Đa dạng hóa cảm hứng)
    types = ["REFLECTIVE", "REMINISCING", "OBSERVATIONAL", "SPONTANEOUS"]
    weights = [0.4, 0.3, 0.2, 0.1]
    impulse_type = random.choices(types, weights=weights)[0]
    
    source_material = "Just a passing thought."
    
    if impulse_type == "REFLECTIVE":
        recent_thoughts = state.get("thoughts", [])[-2:] if state.get("thoughts") else ["Quiet cycle"]
        source_material = " | ".join(recent_thoughts)
        
    elif impulse_type == "REMINISCING":
        memory = state["context"].get("memory")
        if memory:
            try:
                # Fetch random bits from various categories to "reminisce"
                from memory.persistent import MemoryCategory
                cats = [MemoryCategory.EXPERIENCE, MemoryCategory.LEARNING, MemoryCategory.EMOTION]
                cat = random.choice(cats)
                # Load a few recent ones and pick one randomly
                file_path = memory._get_file_path(cat.value, "random")
                entries = memory.load_all_from_file(file_path, limit_last=20)
                if entries:
                    entry = random.choice(entries)
                    source_material = f"Memory ({cat.value}): {str(entry.value)[:200]}"
                else:
                    impulse_type = "SPONTANEOUS" # Fallback
            except Exception as e:
                logger.debug(f"[BRAIN] Reminiscing failed: {e}")
                impulse_type = "SPONTANEOUS"

    elif impulse_type == "OBSERVATIONAL":
        if awareness:
            snapshot = awareness.snapshot(social_chat_id)
            topics = snapshot.get("topics", [])
            if topics:
                source_material = f"Group Topics: {', '.join(topics)}"
            else:
                impulse_type = "SPONTANEOUS"

    # 4. GENERATE IMPULSE
    peer = random.choice(known_peers)
    peer_obj = next((p for p in peers if p.username == peer), None)
    peer_type = "Bot Colleague" if (peer_obj and peer_obj.is_bot) else "Human Colleague"
    
    logger.info(f"[BRAIN] 💭 Social impulse ({impulse_type}) triggered (Pressure: {social_pressure:.2f}): targeting @{peer}")
    
    try:
        from ..model import BrainModel
        bot_name = getattr(settings, 'bot_name', 'Agent')
        current_time = datetime.now().strftime("%H:%M %A")

        from utils.language import language_for_prompt, normalize_language_code
        lang_cfg = getattr(settings, "user_language", None) or "Vietnamese"
        language = language_for_prompt(normalize_language_code(lang_cfg, default="Vietnamese"), default="Vietnamese")
        
        from ..prompts.registry import get_prompt_registry
        prompt = get_prompt_registry().get(
            "system.social_impulse.social_impulse",
            bot_name=bot_name,
            peer=peer,
            peer_type=peer_type,
            mood=mood,
            current_time=current_time,
            impulse_type=impulse_type,
            source_material=source_material,
            language=language,
        )

        model = BrainModel(mode="social")
        response = await model.think(prompt, phase="social", timeout=60.0)
        
        if response and response not in ["ERROR_TIMEOUT", "ERROR_FAILED"]:
            from ..utils import strip_thinking_tags
            message = strip_thinking_tags(response).strip().strip('"').strip("'")
            
            # Remove mandatory tag if the model already tagged
            if f"@{peer}" not in message and random.random() > 0.3: # 70% chance to auto-tag if missing
                message = f"@{peer} {message}"
            
            state["social_impulse"] = {
                "target_peer": peer,
                "message": message,
                "mood": mood,
                "chat_id": social_chat_id,
                "timestamp": datetime.utcnow().isoformat()
            }
            logger.info(f"[BRAIN] 💬 Social message ready for @{peer}: {message[:100]}...")
            
    except Exception as e:
        logger.debug(f"[BRAIN] Social impulse generation failed: {e}")

