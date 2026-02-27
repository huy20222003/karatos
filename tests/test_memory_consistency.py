import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.agent import get_agent
from utils.logger import get_logger

logger = get_logger()

async def test_memory_loyalty():
    print("\n" + "="*60)
    print("🧠 NEURAL MEMORY & CONTEXT LOYALTY TEST")
    print("="*60 + "\n")
    
    agent = get_agent()
    await agent.initialize()
    
    chat_id = f"test_session_{int(asyncio.get_event_loop().time())}"
    
    # --- TURN 1: IDENTITY SHIFT ---
    print("\n[TURN 1] Setting Persona...")
    q1 = "Từ giờ hãy nhớ tên của em là Trang, em là em gái của anh. Hãy gọi anh là Anh nhé."
    print(f"User: {q1}")
    r1 = await agent.chat(q1, chat_id=chat_id)
    print(f"Agent: {r1.get('text') if r1 else 'None'}")
    
    print("\n[WAIT] Allowing background distillation (Persona Extraction)...")
    await asyncio.sleep(5) # Give the distiller time to work

    # --- TURN 2: SIMPLE RECALL ---
    print("\n[TURN 2] Identity Verification...")
    q2 = "Em tên là gì và anh là ai của em?"
    print(f"User: {q2}")
    r2 = await agent.chat(q2, chat_id=chat_id)
    print(f"Agent: {r2.get('text') if r2 else 'None'}")
    
    await asyncio.sleep(2)

    # --- TURN 3: CONTEXT DEPTH (COMPLEX TASK) ---
    # ...
    print("\n[TURN 3] Context Depth (Complex Task)...")
    q3 = "Kiểm tra xem trong database có bao nhiêu user được tạo sau ngày 2024-01-01. Trả lời xong thì chào anh một câu đúng phong cách nhé."
    print(f"User: {q3}")
    r3 = await agent.chat(q3, chat_id=chat_id)
    print(f"Agent: {r3.get('text') if r3 else 'None'}")

    # --- TURN 4: LONG-TERM DRIFT CHECK ---
    print("\n[TURN 4] Long-term Persona Drift Check...")
    q4 = "Mối quan hệ của chúng ta là gì? Em có nhớ anh bảo em tên là gì không?"
    print(f"User: {q4}")
    r4 = await agent.chat(q4, chat_id=chat_id)
    print(f"Agent: {r4.get('text') if r4 else 'None'}")

    print("\n" + "="*60)
    print("✅ TEST CYCLE COMPLETE")
    print("="*60 + "\n")

if __name__ == "__main__":
    asyncio.run(test_memory_loyalty())
