import asyncio
import os
import json
from datetime import datetime
from memory.persistent import PersistentMemory, MemoryCategory, MemoryEntry
from core.brain.nodes.generate import chat_generate_node
from utils.logger import get_logger

logger = get_logger()

async def test_intuition_integration():
    print("\n--- Phase 1: Storage Verification ---")
    base_path = "data/test_intuition"
    # Ensure directory exists
    os.makedirs(base_path, exist_ok=True)
    
    memory = PersistentMemory(base_path=base_path)
    
    # 1. Record an intuition
    hunch = "User's previous reluctance to use Git suggests they might prefer a GUI-based workflow."
    print(f"[TEST] Recording intuition: {hunch}")
    await memory.record_intuition(hunch, "Git preference analysis", 0.8)
    
    # 2. Verify search picks it up
    print("[TEST] Searching for 'Git' in INTUITION category...")
    results = await memory.search(query="Git", category=MemoryCategory.INTUITION)
    
    found = False
    for r in results:
        val_str = str(r.value)
        if "reluctance to use Git" in val_str:
            found = True
            print(f"PASSED: Intuition retrieved: {val_str[:100]}...")
            break
    
    if not found:
        print("FAILED: Intuition not found in search results.")
        return

    print("\n--- Phase 2: Brain Injection Verification ---")
    # 3. Simulate chat_generate_node context injection
    # IMPORTANT: Use 'Git' in user_message to ensure BM25 match
    state = {
        "user_message": "Tell me about Git management.",
        "chat_id": "test_user_001",
        "history": [],
        "logic": "Initial technical reasoning.",
        "thought": "User wants Git info.",
        "bot_name": "Niva",
        "bot_pronoun": "em",
        "user_pronoun": "anh",
        "current_time": "2026-02-28 00:00:00",
        "mood": "Stable",
        "energy": "High",
        "language": "Vietnamese",
        "context": {
            "memory": memory
        }
    }
    
    from core.brain.nodes.generate import chat_generate_node
    
    print("[TEST] Running chat_generate_node to check 'logic' field injection...")
    
    try:
        result_state = await chat_generate_node(state)
        
        # In generate.py, user_context (including INTUITION) is appended to logic
        logic_output = result_state.get("logic", "")
        if "INTERNAL INTUITION (HUNCHES)" in logic_output and "GUI-based workflow" in logic_output:
            print("PASSED: Intuition successfully injected into 'logic' field.")
            print("\nLogic Output snippet:")
            print("--------------------------------------------------")
            start = logic_output.find("### INTERNAL INTUITION")
            print(logic_output[start:start+400])
            print("--------------------------------------------------")
        else:
            print("FAILED: Intuition header or content missing from 'logic' field.")
            print("DEBUG logic_output:", logic_output)
    except Exception as e:
        print(f"FAILED: chat_generate_node crashed: {e}")
        import traceback
        traceback.print_exc()

    print("\n--- SUMMARY ---")
    print("Intuition Integration verification completed.")

if __name__ == "__main__":
    asyncio.run(test_intuition_integration())
