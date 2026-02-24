import asyncio
import sys
import os
import json
from pathlib import Path
from dotenv import load_dotenv

# Load env from agent/.env
load_dotenv(Path(__file__).parent.parent / ".env")

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from skills.registry import get_skill_registry
from core.brain.prompts.registry import get_prompt_registry

async def run_skill_test(realm_name, tool_name, params=None):
    params = params or {}
    print(f"\n[Test] {realm_name}:{tool_name}")
    registry = get_skill_registry()
    
    try:
        # For dynamic skills, tool_name is the skill name (e.g. EXECUTE, CODER)
        result = await registry.dispatch(tool_name, params)
        if result and result.get("status") == "success":
            print(f"  ✅ SUCCESS: {result.get('message', 'No message')}")
            data = result.get("data") or result.get("content") or result.get("files")
            if data:
                print(f"  📊 Data snippet: {str(data)[:200]}...")
            return True
        else:
            msg = result.get("message") if result else "No result returned"
            print(f"  ❌ FAILED: {msg}")
            if result and "error_type" in result:
                print(f"  ⚠️ Error Type: {result.get('error_type')}")
            return False
    except Exception as e:
        print(f"  💥 CRASHED: {e}")
        import traceback
        traceback.print_exc()
        return False

async def main():
    print("="*60)
    print("🚀 NivaSound Skill Ecosystem Verification Suite")
    print("="*60)
    
    registry = get_skill_registry()
    print(f"Loaded {len(registry.dynamic_skills)} dynamic skills.")
    
    tests = [
        # (Realm, ToolName, Params)
        ("SYSTEM", "execute", {"command": "dir" if os.name == 'nt' else "ls"}),
        ("SYSTEM", "health_check", {"check_type": "QUICK"}),
        ("SYSTEM", "clear_cache", {"scope": "SHORT_TERM"}),
        ("SYSTEM", "coder", {"action": "LIST", "file_path": "."}),
        ("SYSTEM", "git_control", {}),
        ("WEB", "research", {"topic": "AI Agent security", "depth": "SEARCH"}),
        ("DATA", "dynamic_db", {"query": "liệt kê 3 user đầu tiên"}),
        ("SECURITY", "security_audit", {"limit": 1}),
    ]
    
    results = []
    for realm, tool, params in tests:
        success = await run_skill_test(realm, tool, params)
        results.append((f"{realm}:{tool}", success))
        
    print("\n" + "="*60)
    print("🏁 FINAL REPORT")
    print("="*60)
    all_pass = True
    for name, success in results:
        status_icon = "✅" if success else "❌"
        print(f"{status_icon} {name}")
        if not success: all_pass = False
        
    if all_pass:
        print("\n✨ ALL SKILLS VERIFIED SUCCESSFULLY! ✨")
    else:
        print("\n⚠️ SOME SKILLS FAILED VERIFICATION. Please check logs.")

if __name__ == "__main__":
    asyncio.run(main())
