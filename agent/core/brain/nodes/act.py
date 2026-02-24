import asyncio
from typing import List, Any
from ..state import ChatState
from utils.logger import get_logger

logger = get_logger()

async def chat_act_node(state: ChatState) -> ChatState:
    """
    UNIVERSAL ACTION: Dispatch to the chosen Skill Realm.
    Supports Parallel Execution.
    """
    logger.debug(f"[NEURAL_ACT] Starting action execution for {len(state.get('decision', [])) if isinstance(state.get('decision'), list) else 1} tasks...")
    # Support Parallel Execution (List of decisions)
    decisions = state.get("decision")
    if not isinstance(decisions, list):
        decisions = [decisions] if decisions else []

    if not decisions:
         state["action_result"] = None
         state["phase"] = "acted"
         return state

    from skills.registry import get_skill_registry
    registry = get_skill_registry()
    
    tasks = []
    
    # --- NGO: Tool Result Caching ---
    # Avoid redundant calls if the exact same params were executed recently
    cache = state["context"].get("tool_cache", {})
    # --------------------------------
    
    for d in decisions:
        # Robust key extraction: try action -> task -> skill
        skill_name = d.get("action", d.get("task", d.get("skill", "NONE"))).lower()
        if skill_name == "none" and d.get("skill"):
            # Legacy fallback
            skill_name = d.get("skill").lower()

        if skill_name in ["search", "research", "deep_research"]:
            skill_name = f"web_{skill_name}"
            
        params = d.get("params", {})
        
        # Cache Key
        cache_key = f"{skill_name}:{str(params)}"
        if cache_key in cache:
            logger.info(f"[NGO] Tool Cache Hit: {cache_key}")
            tasks.append(asyncio.sleep(0, result=cache[cache_key]))
            continue

        # Validate Task
        if skill_name in ["none", "reply_directly", "ignore"]:
            if d.get("override"):
                logger.info(f"[NEURAL_ACT] Action suppressed by Critic: {d.get('original_action')} -> {skill_name}")
            else:
                 logger.warning(f"[NEURAL_ACT] Skipping invalid task: Skill={skill_name}")
            tasks.append(asyncio.sleep(0, result=None)) 
            continue 
            
        safe_skill = skill_name
        
        # --- NGO: Internal Alert Handling ---
        # Handle Critic 'ALERT' or system 'comm_alert' as first-class actions
        if safe_skill in ["alert", "comm_alert"]:
            target_id = d.get("target_id") or "ADMIN"
            reason = d.get("reason", "No reason provided")
            original_action = d.get("original_action", "Unknown")
            
            alert_msg = f"🚨 **INTERNAL ALERT**:\nTarget: {target_id}\nAction blocked: {original_action}\nReason: {reason}"
            logger.warning(alert_msg)
            
            # Send notification via Centralized Manager (Phase 24)
            try:
                from utils.notification import NotificationManager
                await NotificationManager.send_alert(
                    title="CRITIC ALERT" if safe_skill == "alert" else "SYSTEM ALERT",
                    body=f"Target: {target_id}\nAction: {original_action}\nReason: {reason}",
                    severity="critical" if safe_skill == "alert" else "warning"
                )
            except Exception as e:
                logger.error(f"[NEURAL_ACT] Failed to send alert notification: {e}")
            
            # Record result
            tasks.append(asyncio.sleep(0, result={"status": "success", "message": "Alert processed internally."}))
            continue
        # ------------------------------------
        
        # --- Phase 19.2: Inject Speculative Context ---
        if state.get("speculative_data_context"):
            params["speculative_data_context"] = state["speculative_data_context"]
        # ---------------------------------------------
        
        logger.info(f"[NEURAL_ACT] Dispatching to Skill: {safe_skill}")
        try:
            tasks.append(registry.dispatch(safe_skill, params))
        except Exception as e:
            logger.error(f"[NEURAL_ACT] Dispatch error: {e}")
            tasks.append(asyncio.sleep(0, result=f"Error dispatching to {safe_skill}: {e}"))

    try:
        if len(tasks) == 0:
            result = []
        elif len(tasks) == 1:
            result = await tasks[0]
            # Update cache
            if results_to_cache := result:
                cache[cache_key] = results_to_cache
            
            # --- CLI Approval Flow (Phase 24: Centralized Notification) ---
            if isinstance(result, dict) and result.get("status") == "pending" and result.get("message") == "APPROVAL_REQUIRED":
                from utils.notification import NotificationManager
                logger.info(f"[NEURAL_ACT] Triggering centralized CLI approval for: {result.get('command')}")
                await NotificationManager.request_approval(
                    command=result.get("command"), 
                    reason=result.get("details", "Nghi ngờ bảo mật")
                )
            # --------------------------

        else:
            # ALGORITHMIC PARALLELISM: Execute all independent streams at once
            result = await asyncio.gather(*tasks)
            
            # Check for any pending actions in parallel execution
            for r in result:
                if isinstance(r, dict) and r.get("status") == "pending" and r.get("message") == "APPROVAL_REQUIRED":
                    from utils.notification import NotificationManager
                    await NotificationManager.request_approval(
                        command=r.get("command"), 
                        reason=r.get("details", "Nghi ngờ bảo mật")
                    )
            
        state["action_result"] = result
        state["context"]["tool_cache"] = cache
    except Exception as e:
        logger.error(f"[NEURAL_ACT] Execution failed: {e}")
        state["action_result"] = f"ERROR: {str(e)}"

    state["phase"] = "acted"
    return state

async def chat_collect_result_node(state: ChatState) -> ChatState:
    """
    Collect the result of the current task and move to the next step.
    """
    result = state.get("action_result")
    state["task_outputs"].append(result)
    state["current_step"] += 1
    
    logger.info(f"[NEURAL_COLLECT] Task {state['current_step']} complete. Result captured.")
    state["phase"] = "result_collected"
    return state
