from dotenv import load_dotenv
from pathlib import Path
load_dotenv(Path(__file__).parent.parent / ".env")

import asyncio
import os
import sys

# Ensure agent directory is in python path
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
load_dotenv(Path(__file__).parent.parent / ".env")

from core.agent import get_agent
from utils.logger import get_logger

logger = get_logger()

async def main():
    print("Initialize Agent...")
    agent = get_agent()
    await agent.initialize()
    
    # User message 1
    msg1 = "Hãy tạo cho tôi một skill mới tên là 'calculate_math' để tính toán biểu thức toán học cơ bản nhé."
    print(f"\nUser: {msg1}\n")
    
    chat_id = "console_tester"
    # Pass is_test: True to run synchronously
    response_data1 = await agent.chat(msg1, chat_id, context={"is_test": True})
    
    if response_data1:
        text = response_data1.get("text", str(response_data1))
        print(f"Agent (Sync): {text}\n")
    else:
        print("Agent: [No Response]")

    # User message 2
    msg2 = "Bây giờ hãy sử dụng skill 'calculate_math' đó để tính 1111 * 2222 giúp tôi"
    print(f"\nUser: {msg2}\n")
    response_data2 = await agent.chat(msg2, chat_id, context={"is_test": True})
    
    if response_data2:
        text = response_data2.get("text", str(response_data2))
        print(f"Agent (Sync): {text}\n")
    else:
        print("Agent: [No Response]")

if __name__ == "__main__":
    import logging
    logging.getLogger().setLevel(logging.INFO)
    asyncio.run(main())
