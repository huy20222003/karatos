import asyncio
from core.brain.model import SharedModelProvider
from utils.logger import get_logger

logger = get_logger()

async def generate_memory_critique(user_message: str, raw_memories: list) -> str:
    """
    Phase 5: Critical Recall (Memory Critic).
    Generates an inner monologue critiquing past actions before responding.
    """
    if not raw_memories:
        return ""
        
    model = SharedModelProvider.get_model()
    
    # We expect raw_memories to be a list of MemoryEntry objects or strings
    memory_text = ""
    for idx, m in enumerate(raw_memories[:3]):
        val = getattr(m, 'value', str(m))
        memory_text += f"Memory {idx+1}: {val}\n"
    
    if not memory_text.strip():
        return ""
        
    prompt = f"""
You are an AI's inner monologue (Memory Critic). 
Your job is to critically evaluate retrieved past memories to ensure you don't repeat mistakes or give bad advice based on outdated data.
Be extremely brief, critical, and objective. 

User Request: "{user_message}"

Retrieved Past Memories:
{memory_text}

Write a 2-3 sentence internal thought evaluating how reliable and useful these memories are for the CURRENT request. Point out exactly what helps and what is irrelevant/wrong.
"""
    try:
        response = await asyncio.wait_for(model.ainvoke(prompt), timeout=30.0)
        from core.brain.utils import get_llm_content
        critique = get_llm_content(response).strip()
        return f"\n\n[INNER MONOLOGUE - MEMORY CRITIC]: {critique}"
    except Exception as e:
        logger.warning(f"[MEMORY_CRITIC] Failed to generate critique: {e}")
        return ""
