import asyncio
import os
import sys
from datetime import datetime

# Add root to sys.path
sys.path.append(os.getcwd())

from memory.persistent import get_memory, MemoryCategory
from core.brain.nodes.context_critic import context_critic_node
from core.brain.state import ChatState

async def verify():
    print("--- 1. Testing Session-Aware Memory ---")
    memory = get_memory()
    chat_id = "test_chat_123"
    ep1 = "episode_alpha"
    ep2 = "episode_beta"
    
    # Clean old test data if any (not really possible with current MD storage easily, so we use unique IDs)
    now = datetime.utcnow().timestamp()
    chat_id = f"test_chat_{int(now)}"
    
    print(f"Recording messages for {chat_id}...")
    await memory.record_chat_message(chat_id, "user", "Message in Alpha 1", episode_id=ep1)
    await memory.record_chat_message(chat_id, "assistant", "Response in Alpha 1", episode_id=ep1)
    await memory.record_chat_message(chat_id, "user", "Message in Beta 1", episode_id=ep2)
    await memory.record_chat_message(chat_id, "user", "Message in Alpha 2", episode_id=ep1)
    
    print("Fetching history for Episode Alpha...")
    history_alpha = await memory.get_chat_history(chat_id, episode_id=ep1)
    print(f"Alpha count: {len(history_alpha)}")
    for m in history_alpha:
        print(f"  - {m['role']}: {m['content']} (Meta: {m.get('metadata')})")
    
    assert len(history_alpha) == 3
    assert all(m.get('metadata', {}).get('episode_id') == ep1 for m in history_alpha)
    
    print("Fetching history for Episode Beta...")
    history_beta = await memory.get_chat_history(chat_id, episode_id=ep2)
    print(f"Beta count: {len(history_beta)}")
    assert len(history_beta) == 1
    assert history_beta[0]['content'] == "Message in Beta 1"
    
    print("Fetching ALL history (no episode filter)...")
    history_all = await memory.get_chat_history(chat_id)
    print(f"Total count: {len(history_all)}")
    assert len(history_all) == 4
    
    print("\n--- 2. Testing Context Critic History Expansion ---")
    state: ChatState = {
        "chat_id": chat_id,
        "user_message": "Tell me more about Alpha",
        "chat_history": history_alpha,
        "associative_context": "Some memory context",
        "thoughts": [],
        "final_decision": "GENERATE"
    }
    
    # We'll wrap the node call to capture logs if needed, but for now we'll just check if it fails
    # and manually inspect that it doesn't crash with the new larger history.
    print("Running context_critic_node...")
    updated_state = await context_critic_node(state)
    print("Context Critic finished successfully.")
    
    print("\n--- 3. Testing Logic for Planning Bypass ---")
    state_plan: ChatState = {
        "chat_id": chat_id,
        "user_message": "Search for something",
        "chat_history": history_alpha,
        "final_decision": "PLAN",
        "thoughts": []
    }
    updated_state_plan = await context_critic_node(state_plan)
    print("Planning bypass check complete.")

    print("\n[SUCCESS] VERIFICATION COMPLETED")

if __name__ == "__main__":
    asyncio.run(verify())
