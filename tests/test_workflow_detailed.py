import asyncio
import sys
import json
import time
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from core.agent import get_agent
from core.brain.graph import Brain
from utils.logger import get_logger

logger = get_logger()

# Set UTF-8 encoding for stdout
if sys.stdout.encoding != 'utf-8':
    try:
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    except Exception:
        pass

async def run_detailed_workflow_test(query: str):
    print(f"\n{'='*60}")
    print(f"STARTING DETAILED WORKFLOW TEST")
    print(f"Query: '{query}'")
    print(f"{'='*60}\n")

    agent = get_agent()
    print("Step 0: Đang khởi tạo Agent...")
    if not await agent.initialize():
        print("❌ Khởi tạo Agent thất bại!")
        return

    brain = agent.brain
    
    # Chuẩn bị state ban đầu
    initial_state = {
        "chat_id": "test_detailed_workflow",
        "user_message": query,
        "chat_history": [],
        "context": {
            "channel": "terminal",
            "is_test": True, # Đảm bảo chạy đồng bộ để bắt log
            "memory": agent.memory
        },
        "thoughts": [],
        "response": "",
        "phase": "start",
        "plan": [],
        "current_step": 0,
        "task_outputs": []
    }

    print("\n--- BAT DAU QUA TRINH PHAN TICH (BRAIN CYCLE) ---\n")
    
    start_time = time.time()
    current_state = initial_state.copy()
    
    # Sử dụng astream để theo dõi từng node
    async for event in brain.compiled_chat_graph.astream(initial_state):
        for node_name, state_update in event.items():
            t = time.time() - start_time
            print(f"\n[{t:.2f}s] >>> NODE: {node_name.upper()}")
            
            # In input quan trọng của node
            if node_name == "route":
                print(f"      INPUT: User Message='{current_state.get('user_message')}'")
            elif node_name == "plan":
                print(f"      INPUT: Decision='{current_state.get('decision')}', Needs Planning={current_state.get('needs_planning')}")
            elif node_name == "prepare_step":
                print(f"      INPUT: Current Step={current_state.get('current_step')}, Plan Length={len(current_state.get('plan', []))}")
            elif node_name == "act":
                print(f"      INPUT: Decision (Step Action)={current_state.get('decision')}")
            elif node_name == "generate":
                print(f"      INPUT: Task Outputs Count={len(current_state.get('task_outputs', []))}")

            # Cập nhật state hiện tại
            current_state.update(state_update)

            # In toan bo state update de xem chi tiet
            print(f"      OUTPUT (Update): {json.dumps(state_update, indent=2, default=str)[:1000]}")
            if len(str(state_update)) > 1000:
                print("      ... [Output truncated for readability]")

            # In tom tat theo tung node
            if node_name == "parallel_startup":
                print("   [1. Nhan Input & Khoi tao]")
                print(f"      -> Context Keys: {list(state_update.get('context', {}).keys())}")

            elif node_name == "route":
                print("   [2. Bo nao phan tich & 3. Lua chon huong xu ly]")
                print(f"      -> Decision: {state_update.get('decision')}")
                print(f"      -> Confidence: {state_update.get('confidence', 0.0)*100:.1f}%")
                if "thoughts" in state_update and state_update["thoughts"]:
                    print(f"      -> Rationale: {state_update['thoughts'][-1]}")

            elif node_name == "plan":
                print("   [4. Lap ke hoach (Plan)]")
                steps = state_update.get("plan", [])
                print(f"      -> Steps Generated: {len(steps)}")
                for i, step in enumerate(steps):
                    print(f"         Step {i+1}: Task='{step.get('task')}', Thought='{step.get('thought')}'")

            elif node_name == "prepare_step":
                print(f"   [Chuan bi thuc hien buoc {current_state.get('current_step', 0) + 1}]")
                if "decision" in state_update and state_update["decision"]:
                    action = state_update["decision"].get("action")
                    print(f"      -> Selected Tool/Skill: {action}")
                    print(f"      -> Args: {state_update['decision'].get('args')}")

            elif node_name == "act":
                print("   [5. Su dung Skill/Tool thuc hien theo Plan]")
                res = state_update.get("action_result")
                if res:
                    print(f"      -> Status: {res.get('status')}")
                    print(f"      -> Message: {res.get('message')}")

            elif node_name == "collect":
                print("   [6. Ket qua thuc hien tu Plan]")
                outputs = state_update.get("task_outputs", [])
                if outputs:
                    last_out = outputs[-1]
                    print(f"      -> Data Captured (Sample): {str(last_out.get('data'))[:200]}...")

            elif node_name == "generate":
                print("   [7. Tong hop ket qua]")
                # Explicitly show what is being passed to synthesis
                outputs = current_state.get("task_outputs", [])
                print(f"      -> Kiem tra du lieu dau vao (task_outputs): {len(outputs)} item(s)")
                for idx, out in enumerate(outputs):
                    # Show the content accurately like chat_generate_node does
                    content = out.get('data') or out.get('content') or out.get('text') or out
                    data_preview = json.dumps(content, indent=2, default=str)[:500]
                    print(f"         Item {idx+1} content: {data_preview}...")
                print(f"      -> Final Response Length: {len(state_update.get('response', ''))}")

            elif node_name == "post_generate":
                print("   [Hoan tat & Luu tru]")
                resp = current_state.get("response", "")
                print(f"\n{'='*20} CAU TRA LOI CUOI CUNG {'='*20}")
                print(resp)
                print(f"{'='*60}")

    print(f"\nKiem tra hoan tat trong {time.time() - start_time:.2f}s")

if __name__ == "__main__":
    # Chọn query cần test: Database query để kiểm tra Shadowing
    TEST_QUERY = "liệt kê 5 user đầu tiên"
    
    try:
        asyncio.run(run_detailed_workflow_test(TEST_QUERY))
    except Exception as e:
        print(f"\nLOI TRONG QUA TRINH TEST: {e}")
        import traceback
        traceback.print_exc()
