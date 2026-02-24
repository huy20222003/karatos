import asyncio
import time
import sys
import os
import json
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from utils.logger import get_logger
from config.settings import settings
from core.brain.nodes.router import RouterModel
from core.brain.nodes.plan import chat_plan_node
from skills.registry import get_skill_registry
from core.brain.nodes.generate import GeneratorModel

import logging
logger = get_logger()
logging.getLogger().setLevel(logging.DEBUG)

async def run_pipeline_test(user_query: str):
    print(f"\n{'='*50}")
    print(f"🚀 STARTING PIPELINE TEST: '{user_query}'")
    print(f"{'='*50}\n")
    
    start_total = time.time()

    # 1. ROUTER PHASE
    print("\n[1] ROUTER PHASE...")
    t0 = time.time()
    router = RouterModel()
    
    # Mock efficient state
    msg = user_query
    history_str = f"USER: {msg}"
    
    # 1.1 Load Prompt Registry
    from core.brain.prompts.registry import get_prompt_registry
    p_registry = get_prompt_registry()
    
    # 1.2 Build Rules Prompt (Replicating chat_route_node logic)
    prompt = p_registry.get("system.router.routing_logic",
                          msg=msg,
                          history_str=history_str,
                          skills_compact="- DATA:ANALYZE: Query database",
                          hint="",
                          mood="OPTIMISTIC",
                          energy="100%")
                          
    print(f"   -> Full Prompt Size: {len(prompt)}")
    
    # 1.3 Send to Model
    response = await router.think(prompt)
    
    # 1.4 Parse using new Tag Protocol
    from core.brain.utils import extract_json, extract_tag
    from core.brain.utils import strip_thinking_tags
    clean_response = strip_thinking_tags(response)
    
    # Simulate Router logic
    decision = extract_tag(clean_response, "decision") or "PLAN"
    intent = extract_tag(clean_response, "intent") or "Data Retrieval"
    
    snippet = clean_response[:200].replace('\n', ' ')
    print(f"   -> Raw Response Snippet: {snippet}...")
    print(f"   -> Decision: {decision}")
    print(f"   -> Intent: {intent}")
    print(f"   -> Time: {time.time()-t0:.2f}s")
    
    if decision not in ["PLAN"]:
        print("   -> Stopping here (Not a Data Query).")
        return

    # 1.5 PLANNER PHASE
    print("\n[1.5] PLANNER PHASE...")
    t0 = time.time()
    # Mocking state for planner
    plan_state = {
        "user_message": user_query,
        "chat_history": [],
        "chat_id": 12345,
        "context": {"memory": []},
        "mood": "OPTIMISTIC",
        "energy_level": 1.0
    }
    
    plan_result = await chat_plan_node(plan_state)
    print(f"   -> Planning Thought: {plan_result.get('planning_thought')}")
    plan = plan_result.get("plan", [])
    print(f"   -> Steps generated: {len(plan)}")
    for i, step in enumerate(plan):
        print(f"      Step {i+1}: {step.get('task')} -> {step.get('thought')}")
    
    if not plan:
        print("   -> Planner failed to generate steps. Using reflex fallback for pipeline test.")
        # Manual fallback for the rest of the test if needed, but the goal is to see it SUCCEED

    # 2. DATA REALM (CODE GEN & EXECUTION)
    print("\n[2] DATA REALM (DYNAMIC DB)...")
    t0 = time.time()
    registry = get_skill_registry()
    
    # Execute dynamic_db skill
    result_package = await registry.dispatch("dynamic_db", {"query": user_query})
    t1 = time.time()
    
    if result_package.get("status") == "error":
        print(f"   -> DataRealm Error: {result_package.get('message')}")
        if "code_used" in result_package:
             print(f"   -> Last SQL attempted: {result_package.get('code_used')}")
        return

    generated_code = result_package.get("code_used", "N/A")
    result_data = result_package.get("data", "N/A")
    
    print(f"   -> Generated SQL:\n{'-'*20}\n{generated_code}\n{'-'*20}")
    print(f"   -> Raw Data Results count: {len(result_data) if isinstance(result_data, list) else 0}")
    print(f"   -> Time: {t1-t0:.2f}s")
    
    # 3. GENERATOR (SYNTHESIS)
    print("\n[3] GENERATOR (SYNTHESIS)...")
    t0 = time.time()
    generator = GeneratorModel()
    
    # Prepare inputs
    prompt = f"""
    The user asked: "{user_query}"
    
    Here is the results found in the database:
    {json.dumps(result_data, indent=2, default=str)}
    
    Please synthesize a natural, helpful response for the user (in Vietnamese).
    If it's a list of users, display them nicely (maybe in a table-like format).
    """
    
    response = await generator.think(prompt, phase="synthesis")
    t1 = time.time()
    
    print(f"   -> Final Response:\n{'-'*50}\n{response}\n{'-'*50}")
    print(f"   -> Time: {t1-t0:.2f}s")
    
    end_total = time.time()
    print(f"\n{'='*50}")
    print(f"✅ E2E PIPELINE COMPLETE in {end_total-start_total:.2f}s")
    print(f"{'='*50}\n")

if __name__ == "__main__":
    # Test 1: Data Retrieval
    QUERY = "liệt kê 5 user đầu tiên được tạo trên hệ thống"
    
    # Test 2: Curly Brace Formatting Fix
    BRACE_QUERY = "Nêu ý nghĩa của dấu ngoặc nhọn { } trong JSON"
    
    async def run_tests():
        await run_pipeline_test(QUERY)
        print("\n" + "#"*50)
        print("🧪 TESTING FORMATTING FIX WITH CURLY BRACES")
        print("#"*50)
        await run_pipeline_test(BRACE_QUERY)

    try:
        asyncio.run(run_tests())
    except KeyboardInterrupt:
        print("\nTest stopped by user.")
    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
