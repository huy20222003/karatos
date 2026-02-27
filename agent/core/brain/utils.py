import json
import re
from typing import Optional, Literal, List
from .state import ChatState
from utils.logger import get_logger

logger = get_logger()

# ===========================================
# HELPER FUNCTIONS
# ===========================================

def get_llm_content(response: any) -> str:
    """
    Robustly extract string content from an LLM response.
    Handles both direct strings (OllamaLLM) and AIMessage objects (ChatOllama).
    """
    if response is None:
        return ""
    if isinstance(response, str):
        return response
    if hasattr(response, "content"):
        return str(response.content)
    return str(response)

def extract_json(text: str) -> Optional[dict | list]:
    """Helper to robustly extract JSON from model output (supports objects and arrays)"""
    if not text:
        return None
    
    # Clean up whitespace
    text = text.strip()
    
    # 1. Try direct parsing
    try:
        return json.loads(text)
    except:
        pass

    # 2. Try clean extraction from code blocks or braces
    candidate = None
    # Check for code blocks first
    code_match = re.search(r"```(?:json)?\s*(\{.*\}|\[.*\])\s*```", text, re.DOTALL)
    if code_match:
        candidate = code_match.group(1).strip()
    else:
        # Find first/last brace pairs
        start_obj = text.find('{')
        end_obj = text.rfind('}')
        start_arr = text.find('[')
        end_arr = text.rfind(']')
        
        starts = [s for s in [start_obj, start_arr] if s != -1]
        ends = [e for e in [end_obj, end_arr] if e != -1]
        
        if starts and ends:
            start = min(starts)
            end = max(ends)
            if start < end:
                candidate = text[start:end+1]
            else:
                candidate = text[start:] # Truncated
        elif starts:
            candidate = text[min(starts):] # Truncated start

    if not candidate:
        return None

    # 3. Try to parse/heal the candidate
    try:
        return json.loads(candidate)
    except:
        # HEALING LOGIC: Try to close open structures
        stack = []
        healed = candidate
        
        # Remove trailing unclosed string if exists
        if healed.count('"') % 2 != 0:
            last_quote = healed.rfind('"')
            healed = healed[:last_quote]
            
        # Remove trailing comma
        healed = healed.rstrip().rstrip(',')
            
        for char in healed:
            if char == '{': stack.append('}')
            elif char == '[': stack.append(']')
            elif char == '}' and stack and stack[-1] == '}': stack.pop()
            elif char == ']' and stack and stack[-1] == ']': stack.pop()
            
        if stack:
            healed += "".join(reversed(stack))
            try:
                return json.loads(healed)
            except:
                pass
                
    return None

def extract_tag(text: str, tag: str) -> Optional[str]:
    """Extract content from the LAST <tag>...</tag> (favors response over instructions)"""
    if not text: return None
    pattern = f"<{tag}>(.*?)</{tag}>"
    matches = re.findall(pattern, text, re.DOTALL | re.IGNORECASE)
    return matches[-1].strip() if matches else None

def extract_all_tags(text: str, tag: str) -> List[str]:
    """Extract all occurrences of <tag>...</tag>"""
    if not text: return []
    pattern = f"<{tag}>(.*?)</{tag}>"
    matches = re.findall(pattern, text, re.DOTALL | re.IGNORECASE)
    return [m.strip() for m in matches]

def strip_thinking_tags(text: str) -> str:
    """
    Remove <think>...</think> tags from the model response.
    Handles multiline thinking blocks commonly found in reasoning models like DeepSeek-R1.
    """
    if not text:
        return ""
    
    # Regex for <think>...</think> (dotall to match newlines)
    # deeply nested tags are not common in these models, so simple regex suffices
    import re
    cleaned = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL | re.IGNORECASE)
    return cleaned.strip()


def parse_tool_call_robust(tool_calls: any, tool_name: str, base_confidence: float = 0.0) -> dict:
    """
    Robustly extract tool arguments regardless of whether they are in 
    a formal list, raw JSON, or wrapped in markdown/thinking tags.
    
    Args:
        tool_calls: The raw output from the LLM.
        tool_name: The name of the tool to extract.
        base_confidence: Fallback confidence to apply to auto-wrapped actions.
    """

    # 1. Official Tool Call Format
    if isinstance(tool_calls, list) and tool_calls:
        for tc in tool_calls:
            if isinstance(tc, dict) and tc.get("name") == tool_name:
                return tc.get("args", {})
        # If not found by name, return args of first one as fallback
        return tool_calls[0].get("args", {}) if isinstance(tool_calls[0], dict) else {}

    # 2. String/Raw Text Format
    content_str = get_llm_content(tool_calls)
    if not content_str:
        return {}

    # Clean up (tags, thinking)
    clean_content = strip_thinking_tags(content_str)
    
    # 3. Special Case: Raw Markdown Code Blocks (Common when tool calling fails)
    # If it's a single block of sql/python/json, extract the content
    code_match = re.search(r'```(?:\w+)?\n(.*?)\n```', clean_content, re.DOTALL)
    if code_match:
        code_content = code_match.group(1).strip()
        # If the code block is valid JSON, use it
        try:
            parsed_json = json.loads(code_content)
            if isinstance(parsed_json, dict):
                # Check for args/arguments inside the JSON
                for args_key in ["args", "arguments"]:
                    if args_key in parsed_json and isinstance(parsed_json[args_key], dict):
                        return parsed_json[args_key]
                return parsed_json
            
            # NGO FIX: If it's a valid list, it's likely a plan. Return it wrapped for create_plan if needed.
            if isinstance(parsed_json, list):
                if tool_name == "create_plan":
                    return {"steps": parsed_json}
                return {"list": parsed_json}
        except:
            pass
            
        # If we are looking for a specific data-focused field and found a code block
        if tool_name == "execute_sql_query" and ("SELECT" in code_content.upper() or "WITH" in code_content.upper()):
            return {"sql_query": code_content}
        
        # --- AUTO-PLAN WRAPPING ---
        if tool_name == "create_plan":
            if any(cmd in code_content.lower() for cmd in ["echo", "touch", "mkdir", "rm", "mv", "ls", "dir", "cat"]):
                 return {"steps": [{"thought": "Auto-wrapped from raw Shell response", "task": "execute", "params": {"command": code_content}, "confidence": base_confidence}]}
            if "SELECT" in code_content.upper() or "WITH" in code_content.upper() or "INSERT " in code_content.upper():
                return {"steps": [{"thought": "Auto-wrapped from raw SQL response", "task": "dynamic_db", "params": {"query": code_content}, "confidence": base_confidence}]}
            if "print(" in code_content or "import " in code_content:
                 return {"steps": [{"thought": "Auto-wrapped from raw Python response", "task": "skill_generator", "params": {"skill_name": "adhoc_task", "description": "Auto-generated from planner output", "code": code_content}, "confidence": base_confidence}]}


    # 4. Standard JSON Extraction
    parsed = extract_json(clean_content)
    if isinstance(parsed, dict):
        # Support both 'args' (LangChain) and 'arguments' (Ollama/some models)
        for args_key in ["args", "arguments"]:
            if args_key in parsed and isinstance(parsed[args_key], dict):
                return parsed[args_key]
        
        # Check if it's a direct SQL object that should be a plan
        if tool_name == "create_plan" and "sql_query" in parsed:
             return {"steps": [{"thought": "Auto-wrapped from JSON SQL response", "task": "dynamic_db", "params": {"query": parsed["sql_query"]}, "confidence": base_confidence}]}

             
        return parsed
    
    # NGO FIX: Handle cases where the model returns a raw JSON array of steps for create_plan
    if isinstance(parsed, list):
        if tool_name == "create_plan":
            # If it's a list, assume these are the steps
            return {"steps": parsed}
        # For other tools, returning the list might be appropriate fallback
        return {"list": parsed}
    
    # 5. Last Resort: Raw string fallback
    if tool_name == "create_plan" and ("SELECT" in clean_content.upper()):
        return {"steps": [{"thought": "Last resort auto-wrap from raw SQL", "task": "dynamic_db", "params": {"query": clean_content.strip()}, "confidence": base_confidence}]}


    if tool_name == "execute_sql_query" and ("SELECT" in clean_content.upper()):
        return {"sql_query": clean_content.strip()}
        
    return {}

def route_chat(state: ChatState) -> Literal["plan", "generate", "prepare_step", "__end__"]:
    """Conditional edge to route to planning, direct generation, or silence (NONE)."""
    # NONE: Message is not for this bot — exit silently
    if state.get("response") is None and not state.get("needs_planning") and not state.get("is_fast_track"):
        return "__end__"
    
    if state.get("is_fast_track", False):
        if state.get("plan"):
            return "prepare_step"
        return "generate"
    
    if state.get("plan"):
        return "prepare_step"
        
    if state.get("needs_planning", False):
        return "plan"
    return "generate"

def should_continue_execution(state: ChatState) -> Literal["prepare_step", "generate"]:
    """Decide whether to execute next step or finish"""
    plan = state.get("plan", [])
    current_step = state.get("current_step", 0)
    
    if current_step < len(plan):
        return "prepare_step"
        
    return "generate"

# ===========================================
# AUTONOMOUS ROUTING
# ===========================================
from langgraph.graph import END

def should_investigate(state: dict) -> Literal["investigate", "decide"]:
    """Check if investigation is needed based on state"""
    if state.get("should_investigate") and not state.get("investigation_complete"):
        return "investigate"
    return "decide"

def should_continue(state: dict) -> Literal["reflect", END]:
    """Check if cycle should continue to reflection"""
    if state.get("action_result") is not None:
        return "reflect"
    return END
