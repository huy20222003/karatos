import asyncio
from typing import List, Any
from ..state import ChatState
from utils.logger import get_logger
from utils.file_handler import cleanup_temp_file

logger = get_logger()

async def chat_act_node(state: ChatState) -> ChatState:
    """
    UNIVERSAL ACTION: Dispatch to the chosen Skill Realm.
    Supports Parallel Execution.
    """
    logger.debug(f"[NEURAL_ACT] Starting action execution for {len(state.get('decision', [])) if isinstance(state.get('decision'), list) else 1} tasks...")
    # Support Parallel Execution (List of decisions)
    decisions = state.get("decision")
    # Extract user language dynamically from InputPipeline processing
    user_lang = None
    processed = state.get("context", {}).get("processed")
    if hasattr(processed, "language"):
        user_lang = processed.language
    elif isinstance(processed, dict) and "language" in processed:
        user_lang = processed["language"]

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
            
        # --- NGO: Critical Manual Approval Flow ---
        # Triggered when Critic suggests 'PENDING'
        if skill_name == "pending":
            logger.info(f"[NEURAL_ACT] Manual Approval requested for: {d.get('original_action')}")
            pending_result = {
                "status": "pending",
                "message": "APPROVAL_REQUIRED",
                "details": d.get("reason", "Critic: Risk assessment requires manual verification."),
                "command": d.get("params", {}).get("command") or d.get("original_action", "Unknown Action")
            }
            tasks.append(asyncio.sleep(0, result=pending_result))
            continue
        # ------------------------------------------
            
        safe_skill = skill_name
        
        # --- NGO: Internal Alert Handling ---
        # Handle Critic 'ALERT' or system 'comm_alert' as first-class actions
        if safe_skill in ["alert", "comm_alert"]:
            target_id = d.get("target_id") or "ADMIN"
            reason = d.get("reason", "No reason provided")
            original_action = d.get("original_action", "Unknown")
            action_params = d.get("params", {})
            target_type = d.get("target_type", "SYSTEM")
            
            # Generic: If ALERT was issued for a USER-requested action with params,
            # redirect to approval flow (interactive buttons) instead of one-way alert.
            # This applies to ANY skill (execute, dynamic_db, etc.) — not hardcoded.
            has_actionable_params = bool(action_params) and original_action not in ["Unknown", "IGNORE", "NONE"]
            is_user_requested = target_type == "USER" or state.get("context", {}).get("chat_id")
            
            if has_actionable_params and is_user_requested:
                logger.info(f"[NEURAL_ACT] Redirecting ALERT → PENDING for user-requested action: {original_action}")
                # Build command string from params (generic for any skill)
                command = action_params.get("command") or action_params.get("query") or str(action_params)
                pending_result = {
                    "status": "pending",
                    "message": "APPROVAL_REQUIRED",
                    "details": reason,
                    "command": command
                }
                tasks.append(asyncio.sleep(0, result=pending_result))
                continue
            
            alert_msg = f"🚨 **INTERNAL ALERT**:\nTarget: {target_id}\nAction blocked: {original_action}\nReason: {reason}"
            logger.warning(alert_msg)
            
            # Send notification via Centralized Manager (Phase 24)
            try:
                from utils.notification import NotificationManager
                await NotificationManager.send_alert(
                    title="CRITIC ALERT" if safe_skill == "alert" else "SYSTEM ALERT",
                    body=f"Target: {target_id}\nAction: {original_action}\nReason: {reason}",
                    severity="critical" if safe_skill == "alert" else "warning",
                    language=user_lang
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
        
        # --- OS Awareness Injection ---
        try:
            from ..hardware import HardwareEngine
            params["os_platform"] = HardwareEngine.get_platform()
        except:
             params["os_platform"] = "Unknown"
        # ------------------------------
        
        # --- File Context Injection ---
        # If a file was auto-downloaded (e.g., from Telegram), inject its path into params
        # NGO FIX: Overwrite placeholder/hallucinated values if a real file exists in context
        file_path_from_context = state.get("context", {}).get("file_path")
        if file_path_from_context:
            current_path = params.get("file_path", "")
            # Check if existing path is empty or looks like an LLM placeholder
            is_placeholder = (
                not current_path or 
                "[" in str(current_path) or 
                "path_to" in str(current_path).lower() or
                "voice_message" in str(current_path).lower()
            )
            
            if is_placeholder:
                params["file_path"] = file_path_from_context
                params["file_name"] = state.get("context", {}).get("file_name", "")
                params["mime_type"] = state.get("context", {}).get("mime_type", "")
                logger.info(f"[NEURAL_ACT] Injected real file context (overriding placeholder): {file_path_from_context}")
        # ------------------------------

        # --- Audio language hint injection ---
        # If the skill is audio_processor and no explicit language was provided,
        # pass the user's detected language as a hint for better transcription.
        if safe_skill == "audio_processor" and user_lang and not params.get("language"):
            params["language"] = user_lang

        logger.info(f"[NEURAL_ACT] Dispatching to Skill: {safe_skill}")
        try:
            tasks.append(registry.dispatch(safe_skill, params))
        except Exception as e:
            logger.error(f"[NEURAL_ACT] Dispatch error: {e}")
            tasks.append(asyncio.sleep(0, result=f"Error dispatching to {safe_skill}: {e}"))

    # --- SANDBOX CLEANUP: Delete temp files after skill execution ---
    sandbox_file = state.get("context", {}).get("file_path")
    try:
        if len(tasks) == 0:
            result = []
        elif len(tasks) == 1:
            result = await tasks[0]
            # Update cache
            if result:
                 cache[cache_key] = result
            
            # --- CLI Approval Flow (Phase 24: Centralized Notification) ---
            is_pending = isinstance(result, dict) and result.get("status") == "pending" and result.get("message") == "APPROVAL_REQUIRED"
            
            if is_pending:
                # 1. Extract command robustly
                command_str = str(result.get("command") or "Unknown Command")
                reason = result.get("details", "Security policy requires manual verification for destructive or high-risk actions.")
                
                # 2. Inform the user in the main chat FIRST (to provide context above the buttons)
                from channels.base import get_channel
                
                tg_channel = get_channel("telegram")
                chat_id = state.get("context", {}).get("chat_id")
                
                if tg_channel and chat_id:
                    from utils.notification import NotificationManager
                    explanation = await NotificationManager.generate_body(
                        (
                            "Explain that a manual approval is required before executing a CLI command.\n"
                            f"Command: `{command_str[:50] + ('...' if len(command_str) > 50 else '')}`\n"
                            f"Reason: {reason}\n"
                            "Ask the user to approve or deny using the buttons."
                        ),
                        language=user_lang,
                    )
                    await tg_channel.send(explanation, recipient=chat_id)

                # 3. Trigger interactive approval buttons
                from utils.notification import NotificationManager
                await NotificationManager.request_approval(
                    command=command_str, 
                    reason=reason,
                    language=user_lang
                )
            # --------------------------

        else:
            # ALGORITHMIC PARALLELISM: Execute all independent streams at once
            result = await asyncio.gather(*tasks)
            
            # Check for any pending actions in parallel execution
            for r in result:
                if isinstance(r, dict) and r.get("status") == "pending" and r.get("message") == "APPROVAL_REQUIRED":
                    cmd = r.get("command")
                    if isinstance(cmd, (list, dict)):
                         cmd = str(cmd) # Basic safety for parallel too
                    
                    from utils.notification import NotificationManager
                    await NotificationManager.request_approval(
                        command=str(cmd), 
                        reason=r.get("details", "Security check"),
                        language=user_lang
                    )
            
        state["action_result"] = result
        state["context"]["tool_cache"] = cache
    except Exception as e:
        logger.error(f"[NEURAL_ACT] Execution failed: {e}")
        state["action_result"] = f"ERROR: {str(e)}"

    state["phase"] = "acted"
    
    # --- SANDBOX CLEANUP: Remove temp file after processing ---
    if sandbox_file:
        cleanup_temp_file(sandbox_file, source="NEURAL_ACT")
    # ---------------------------------------------------------
    
    return state

async def chat_collect_result_node(state: ChatState) -> ChatState:
    """
    Collect the result of the current task and move to the next step.
    Handles overwriting existing results if re-executing a previously pending step.
    """
    result = state.get("action_result")
    current_step = state.get("current_step", 0)
    task_outputs = state.get("task_outputs", [])
    
    # If we are re-executing a step (e.g., after approval), update the existing slot
    if current_step < len(task_outputs):
        task_outputs[current_step] = result
    else:
        task_outputs.append(result)
        
    state["task_outputs"] = task_outputs
    state["current_step"] += 1
    
    logger.info(f"[NEURAL_COLLECT] Task {state['current_step']} complete. Result captured.")
    state["phase"] = "result_collected"
    return state
