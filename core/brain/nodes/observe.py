from core.brain.state import AgentState, ChatState
from utils.logger import get_logger
from memory.persistent import MemoryCategory
from config.settings import settings

logger = get_logger()

OBSERVE_LANG = {
    'Vietnamese': {
        'brute_force': 'phát hiện tấn công brute force',
        'brute_force_desc': 'Phát hiện {count} lần thử đăng nhập thất bại liên tiếp',
        'vision_instructions': 'Trả lời bằng ngôn ngữ của người dùng (Ví dụ: Tiếng Việt).'
    },
    'English': {
        'brute_force': 'brute_force',
        'brute_force_desc': 'Detected {count} failed attempts',
        'vision_instructions': "Answer in the user's language."
    }
}

def get_lang():
    lang = getattr(settings, "user_language", "English")
    return OBSERVE_LANG.get(lang, OBSERVE_LANG['English'])

async def observe_node(state: AgentState) -> AgentState:
    """
    OBSERVE: Analyze the incoming audit logs
    This node summarizes, identifies patterns, detects reversals, and fetches risk scores
    """
    logger.debug("Processing audit logs...")
    
    logs = state.get("audit_logs", [])
    memory = state["context"].get("memory")
    
    # Simple summary for now
    if not logs:
        is_meditation = state["context"].get("is_meditation", False)
        if not is_meditation:
            logger.info("No audit logs to analyze and not meditation. Ending.")
            state["should_investigate"] = False
            state["phase"] = "observed"
            return state
        else:
            logger.info("MEDITATION MODE: Continuing without audit logs for self-reflection.")
            state["should_investigate"] = False # No threat, but continue to Decider
            state["phase"] = "observed"
            return state

    # Analyze patterns
    anomalies = []
    evidence = []
    
    # Check for rapid failures (Brute Force)
    lt = get_lang()
    failed_attempts = [l for l in logs if l.get("status") == "failed"]
    if len(failed_attempts) > 5:
        anomalies.append({
            "type": lt['brute_force'],
            "description": lt['brute_force_desc'].format(count=len(failed_attempts)),
            "severity": "high"
        })
        
    state["anomalies"] = anomalies
    state["evidence"] = evidence
    state["should_investigate"] = len(anomalies) > 0
    state["phase"] = "observed"
    
    return state


async def chat_observe_node(state: ChatState) -> ChatState:
    import time
    t_start_obs = time.time()
    chat_id = state["chat_id"]
    msg = state["user_message"]

    logger.info(f"[CHAT_OBSERVE] Loading history for {chat_id}")
    
    memory = state["context"].get("memory")
    short_memory = state["context"].get("short_memory")
    
    # 0. Short-Term Memory Update (Add new observation)
    if short_memory:
        short_memory.add_observation(msg)

    # --- PHASE: IMAGE COMPREHENSION ---
    # If user sent an image (either as file or in-memory base64), extract content
    file_path = state.get("context", {}).get("file_path", "")
    image_base64 = state.get("context", {}).get("image_base64", "")
    mime_type = state.get("context", {}).get("mime_type", "")
    
    image_extensions = (".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".tiff")
    is_image = (
        mime_type.startswith("image/") if mime_type else
        file_path.lower().endswith(image_extensions) if file_path else 
        bool(image_base64)
    )
    
    if is_image and (file_path or image_base64):
        try:
            from tools.vision_reader import VisionReader
            logger.info(f"[CHAT_OBSERVE] 🖼️ Image detected (In-memory: {bool(image_base64)}). Extracting content...")
            vision_result = await VisionReader.analyze(
                image_path=file_path,
                image_base64=image_base64,
                mode="analyze",
                prompt=(
                    "You are a vision question-answering engine.\n"
                    f"USER QUESTION: \"{msg}\"\n\n"
                    "TASK:\n"
                    "- Answer the user's question using ONLY the information inside the image.\n"
                    "- If the question asks to summarize or explain a post/article shown in the screenshot, focus on the main article/post body and ignore browser chrome, menus, sidebars, or generic UI.\n"
                    "- If the question asks for a specific field (e.g., price, name, title, rating), return that value exactly as shown.\n"
                    "- If the answer is clearly present, quote it exactly in the original language (do NOT translate).\n"
                    "- If the answer is not present in the image, return the phrase: ANSWER_NOT_FOUND.\n\n"
                    f"INSTRUCTION: {get_lang()['vision_instructions']}\n\n"
                    "OUTPUT FORMAT:\n"
                    "ANSWER: <single short answer or concise summary in the user's language>"
                ),
                mime_type=mime_type,
            )
            if vision_result.get("status") == "success":
                raw_desc = vision_result["data"]["description"].strip()
                extracted = raw_desc
                upper = raw_desc.upper()
                marker = "ANSWER:"
                if "ANSWER:" in upper:
                    idx = upper.find(marker)
                    extracted = raw_desc[idx + len(marker):].strip()
                # Keep both the direct answer and the underlying vision text for transparency
                state["user_message"] = f"{msg}\n\n[IMAGE_ANSWER]: {extracted}"
                state["context"]["vision_answer"] = extracted
                state["context"]["vision_raw"] = raw_desc
                msg = state["user_message"]
                logger.info(f"[CHAT_OBSERVE] ✅ Vision QA complete ({len(extracted)} chars answer)")
            else:
                logger.warning(f"[CHAT_OBSERVE] Vision extraction failed: {vision_result.get('message')}")
                state["context"]["vision_extracted"] = None
        except Exception as e:
            logger.error(f"[CHAT_OBSERVE] VisionReader error: {e}")
    # --- END IMAGE COMPREHENSION ---

    if memory:
        # Use ConversationContextManager for optimized history
        from memory.context import ConversationContextManager
        ctx_manager = ConversationContextManager()
        
        # 1. Load regular chat history (Smarter retrieval via and truncation via manager)
        episode_id = state.get("episode_id")
        history = await memory.get_chat_history(chat_id, episode_id=episode_id)
        
        # --- NGO: NEURAL COMPRESSION (Character-Based Threshold) ---
        # Trigger based on configurable limits in settings
        history_text_for_size = "".join([m.get("content", "") for m in history])
        if (len(history) > settings.context_compression_messages or len(history_text_for_size) > settings.context_compression_chars) and len(msg.split()) > 3:
            logger.info(f"[NGO] Context bloat detected ({len(history_text_for_size)} chars). Triggering Neural Compression.")
            from core.brain.model import SharedModelProvider
            from core.brain.prompts.registry import get_prompt_registry
            model = SharedModelProvider.get_model()
            p_registry = get_prompt_registry()
            
            # Use utility for compression (Phase 27 Associative Cog)
            compressed_text = await ctx_manager.compress_large_context(history_text_for_size, model, p_registry, query=msg)
            
            # Replace old history with summary + last N messages
            compressed_history = [
                {"role": "system", "content": compressed_text}
            ] + history[-settings.context_planning_limit:]
            history = compressed_history
            logger.info("[NGO] Neural Compression complete. Context window optimized.")
        
        state["chat_history"] = history
        logger.debug(f"[DEBUG_MEMORY] Loaded {len(history)} messages for {chat_id}")
        
        # --- FAST-TRACK CHECK ---
        is_fast_track = state.get("is_fast_track", False)
        if is_fast_track:
             logger.info("[CHAT_OBSERVE] Fast-Track detected. Skipping Deep Recall.")
             return state

        # --- PERCEPTUAL MEMORY: Early Pattern Recognition (Human-like Cognition) ---
        # Like a human brain instantly recognizing familiar patterns before conscious thought
        logic_structured = state.get("logic_structured", [])
        try:
            from memory.persistent import MemoryCategory
            
            # HABIT: "I recognize this user's behavioral pattern"
            habits = await memory.search(query=msg, category=MemoryCategory.HABIT, limit=1, min_importance=0.4)
            if habits:
                habit_nodes = []
                for h in habits:
                    val = h.value if isinstance(h.value, str) else str(h.value)
                    habit_nodes.append({"content": val[:150]})
                logic_structured.append({
                    "category": "Pattern Recognition",
                    "icon": "fas fa-fingerprint",
                    "nodes": habit_nodes
                })
                state["_perceived_habits"] = [h.value for h in habits]
                logger.info(f"[CHAT_OBSERVE] 🧠 Perceptual Memory: Recognized {len(habits)} behavioral pattern(s)")
            
            # USER_PROFILE: "I know who this person is"
            prefs = await memory.search(query=f"preferences {state['chat_id']} {msg}", category=MemoryCategory.USER_PROFILE, limit=2, min_importance=0.3)
            if prefs:
                pref_nodes = []
                for p in prefs:
                    val = p.value if isinstance(p.value, str) else str(p.value)
                    pref_nodes.append({"content": val[:150]})
                logic_structured.append({
                    "category": "User Recognition",
                    "icon": "fas fa-id-badge",
                    "nodes": pref_nodes
                })
                state["_perceived_user_profile"] = [p.value for p in prefs]
                logger.info(f"[CHAT_OBSERVE] 👤 Perceptual Memory: Loaded {len(prefs)} user preference(s)")
                
        except Exception as e:
            logger.debug(f"[CHAT_OBSERVE] Perceptual memory recall failed: {e}")
        
        state["logic_structured"] = logic_structured

        # 2. Semantic Recall: Find relevant past memories
        if not msg.strip():
            logger.info("[CHAT_OBSERVE] Empty message. Skipping Semantic Recall.")
            return state

        try:
            q_vec = state.get("query_vector")
            related_memories = await memory.deep_recall(msg, limit=20, query_vector=q_vec)
            
            # Limit context bloat via manager-style truncation
            context_parts = []
            for m in related_memories[:10]:
                val = str(m.value)
                context_parts.append(f"- {ctx_manager.truncate_text(val, 500)}")
            
            state["associative_context"] = "\n".join(context_parts)
            
            # --- PHASE 5: CRITICAL RECALL (Memory Critic) ---
            if related_memories:
                try:
                    from utils.memory_critic import generate_memory_critique
                    critique = await generate_memory_critique(msg, related_memories)
                    if critique:
                        state["associative_context"] += f"\n{critique}"
                        logger.info(f"[CHAT_OBSERVE] Memory Critic appended internal monologue.")
                except Exception as critic_e:
                    logger.warning(f"[CHAT_OBSERVE] Memory Critic failed: {critic_e}")
                    
        except Exception as e:
            logger.error(f"[CHAT_OBSERVE] Semantic search failed: {e}")
    # NGO FIX: Preserve advanced phases during resumption
    if state.get("phase") not in ["planned", "routed"]:
        state["phase"] = "observed"
    
    logger.info(f"[TRACE] chat_observe_node took {time.time() - t_start_obs:.3f}s")
    return state
