import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.input_pipeline import InputPipeline

async def test_input_pipeline():
    pipeline = InputPipeline()
    
    test_cases = [
        {
            "text": "Hello, how are you?",
            "expected_lang": "en",
            "expected_question": True
        },
        {
            "text": "Xin chào, bạn khỏe không?",
            "expected_lang": "vi",
            "expected_question": True
        },
        {
            "text": "This is a simple statement.",
            "expected_lang": "en",
            "expected_question": False
        },
        {
            "text": "Hôm nay trời đẹp quá.",
            "expected_lang": "vi",
            "expected_question": False
        },
        {
            "text": "What is the status of the database?",
            "expected_lang": "en",
            "expected_question": True
        }
    ]
    
    print("\n🚀 Testing InputPipeline...")
    passed = 0
    for case in test_cases:
        try:
            print(f"\nProcessing: '{case['text']}'")
            result = await pipeline.process(case['text'])
            
            lang_ok = result.language == case['expected_lang']
            q_ok = result.fingerprint['has_question'] == case['expected_question']
            
            if lang_ok and q_ok:
                print(f"  ✅ Passed")
                passed += 1
            else:
                print(f"  ❌ Failed: Got lang={result.language}, question={result.fingerprint['has_question']}")
                
        except Exception as e:
            print(f"  ❌ Error: {e}")
            import traceback
            traceback.print_exc()

    print(f"\nSummary: {passed}/{len(test_cases)} cases passed.")
    if passed == len(test_cases):
        print("🎉 All InputPipeline tests passed!")
        return True
    return False

if __name__ == "__main__":
    asyncio.run(test_input_pipeline())
