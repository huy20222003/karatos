import asyncio
import os
import sys
import io
from pathlib import Path
from dotenv import load_dotenv

# Ensure stdout uses UTF-8 to avoid UnicodeEncodeError on Windows
if hasattr(sys.stdout, 'buffer'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# Tìm thư mục gốc của dự án (project root)
agent_dir = Path(__file__).parent.parent
project_root = agent_dir.parent

# Thêm agent_dir vào sys.path để các import như 'from core.agent' hoạt động
sys.path.append(str(agent_dir))
# Load .env từ project root
load_dotenv(project_root / ".env")

from core.agent import get_agent
from utils.logger import get_logger

logger = get_logger()

async def test_workflow():
    print("--- KHỞI TẠO AGENT ---")
    agent = get_agent()
    await agent.initialize()
    
    chat_id = "workflow_tester"
    
    # Kiểm tra xem folder đã thực sự tồn tại chưa (đã được tạo thủ công hoặc tự động)
    ping_pong_path = agent_dir / "skills" / "definitions" / "ping_pong"
    skill_file_path = ping_pong_path / "SKILL.md"
    
    if not skill_file_path.exists():
        print(f"--- CHUẨN BỊ: TẠO FILE TẠI {skill_file_path} ---")
        ping_pong_path.mkdir(parents=True, exist_ok=True)
        with open(skill_file_path, "w", encoding="utf-8") as f:
            f.write("---\nname: \"ping_pong\"\ndescription: \"Phản hồi pong\"\nrouting_examples:\n  - \"ping\"\ninputs:\n  msg: {type: string}\n---\n# Instruction\nTrả lời 'pong' khi thấy 'ping'.")

    print("\n--- BƯỚC 1: XÁC MINH SỰ TỒN TẠI CỦA SKILL ---")
    if skill_file_path.exists():
        print(f"PASS: Tìm thấy {skill_file_path}")
    else:
        print(f"FAIL: Không tìm thấy {skill_file_path}")
        return

    print("\n--- BƯỚC 2: REFRESH AGENT VÀ KIỂM TRA SỬ DỤNG SKILL ---")
    # Re-initialize to reload skills
    await agent.initialize() 
    
    msg2 = "Bây giờ hãy sử dụng skill 'ping_pong' để nói 'ping' với tôi xem nào"
    print(f"User: {msg2}")
    
    response2 = await agent.chat(msg2, chat_id, context={"is_test": True})
    text2 = response2.get("text", str(response2))
    print(f"Agent Response: {text2}\n")
    
    if "pong" in text2.lower():
        print("--- THÀNH CÔNG: SKILL 'PING_PONG' HOẠT ĐỘNG HOÀN HẢO ---")
    else:
        print("--- THẤT BẠI: SKILL KHÔNG ĐƯỢC GỌI HOẶC PHẢN HỒI SAI ---")

if __name__ == "__main__":
    asyncio.run(test_workflow())
