import asyncio
import os
import shutil
from datetime import datetime
from memory.persistent import PersistentMemory, MemoryCategory
from utils.logger import get_logger

logger = get_logger()

async def test_memory_activation():
    # Setup temporary storage
    test_storage = "data/test_storage_activation"
    if os.path.exists(test_storage):
        shutil.rmtree(test_storage)
    
    memory = PersistentMemory(base_path=test_storage)
    
    print("\n--- Phase 1: Specialized Writers ---")
    
    # 1. Test A2A
    print("[TEST] Recording A2A communication...")
    await memory.record_a2a_communication("Agent_B", "Querying system status", "SUCCESS")
    a2a_file = os.path.join(test_storage, "memory", "a2a", "messages.md")
    if os.path.exists(a2a_file):
        print(f"PASSED: A2A file created at {a2a_file}")
    else:
        print(f"FAILED: A2A file not found")

    # 2. Test Intuition
    print("[TEST] Recording Intuition...")
    await memory.record_intuition("User seems to be in a hurry", 0.8, "Conversation flow analysis")
    intuition_file = os.path.join(test_storage, "sys", "intuition", "insights.md")
    if os.path.exists(intuition_file):
        print(f"PASSED: Intuition file created at {intuition_file}")
    else:
        print(f"FAILED: Intuition file not found")

    # 3. Test Vault
    print("[TEST] Storing Secret in Vault...")
    await memory.store_secret("api_key", "sk-123456789", "Deepmind API Key")
    vault_file = os.path.join(test_storage, "vault", "secrets.md")
    if os.path.exists(vault_file):
        print(f"PASSED: Vault file created at {vault_file}")
    else:
        print(f"FAILED: Vault file not found")

    print("\n--- Phase 2: Live Distillation (Silent Categories) ---")
    
    # Simulate a chat that should trigger Emotion and Procedural extraction
    # Note: We need to mock the distiller or use a real one if available.
    # Since we want to test the full logic, let's use the real distiller but it might take time.
    # Alternatively, we can check if record_chat_message properly saves whatever the distiller returns.
    
    chat_id = "test_activation_001"
    role = "assistant"
    content = "I've updated the deployment script. To deploy, just run 'npm run deploy'."
    
    print(f"[TEST] Recording chat message for distillation and evolution...")
    await memory.record_chat_message("test_chat_001", "assistant", "Hello! I'm Niva.")
    
    print("[TEST] Manually saving distilled units (EMOTION, PROCEDURAL, RELATIONSHIP)...")
    await memory.remember("distilled:test:emo", "User expressed joy", MemoryCategory.EMOTION, 0.7)
    await memory.remember("distilled:test:proc", "Deploy process: git push -> npm deploy", MemoryCategory.PROCEDURAL, 0.8)
    await memory.remember("distilled:test:rel", "Strong trust established", MemoryCategory.RELATIONSHIP, 0.9)
    
    emo_file = os.path.join(test_storage, "memory", "emotions", "chronicle.md")
    proc_file = os.path.join(test_storage, "memory", "procedures", "workflows.md")
    rel_file = os.path.join(test_storage, "profiles", "relationships", "bonds.md")
    
    if os.path.exists(emo_file): print(f"PASSED: Emotion file created at {emo_file}")
    else: print(f"FAILED: Emotion file not found")
    
    if os.path.exists(proc_file): print(f"PASSED: Procedural file created at {proc_file}")
    else: print(f"FAILED: Procedural file not found")
    
    if os.path.exists(rel_file): print(f"PASSED: Relationship file created at {rel_file}")
    else: print(f"FAILED: Relationship file not found")

    print("\n--- SUMMARY ---")
    print("Memory Activation verification completed.")

if __name__ == "__main__":
    asyncio.run(test_memory_activation())
