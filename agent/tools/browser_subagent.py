import asyncio
import json
import re
from typing import Any, Optional, Dict, List
from utils.logger import get_logger
from core.brain.model import SharedModelProvider
from core.brain.prompts.registry import get_prompt_registry
from core.brain.utils import extract_json, strip_thinking_tags
from skills.registry import get_skill_registry
from config.settings import settings

logger = get_logger()

async def browser_subagent(TaskName: str, Task: str, RecordingName: str = "browser_interaction", actions: Optional[list[dict]] = None, max_steps: int = 20) -> Any:
    """ Execute a browser task via MCP driver. Tool Discovery Edition. """
    try:
        logger.info(f"[BROWSER_MCP] Starting Task: {TaskName}")
        registry = get_skill_registry()
        mcp_realm = registry.mcp_realm
        if not mcp_realm: return {"status": "error", "message": "MCP Realm not available."}

        def parse_val(v):
            if v is None: return None
            res = v
            if isinstance(v, dict):
                if "value" in v: res = v["value"]
                elif "result" in v:
                    r = v["result"]
                    res = r.get("value") if isinstance(r, dict) else r
                else: res = v.get("content") or str(v)
            if isinstance(res, str):
                match = re.search(r'```json\s*(.*?)\s*```', res, re.DOTALL)
                if match:
                    js = match.group(1).strip()
                    if js == "undefined" or js == "null": return None
                    try: return json.loads(js)
                    except: return js
                if res.startswith("#") or "returned:" in res:
                    q_match = re.search(r'"(.*?)"', res)
                    if q_match: return q_match.group(1)
            return res

        async def capture_state_mcp():
            try:
                await asyncio.sleep(2.0) 
                url_res = await mcp_realm.execute("chrome-devtools:evaluate_script", {"function": "() => window.location.href"})
                title_res = await mcp_realm.execute("chrome-devtools:evaluate_script", {"function": "() => document.title"})
                current_url = str(parse_val(url_res))
                current_title = str(parse_val(title_res))

                # Interactive Map
                js_map = """() => {
                    try {
                        var items = [];
                        var els = document.querySelectorAll('input, button, a, select, textarea');
                        for (var i = 0; i < els.length; i++) {
                            var el = els[i];
                            var nid = i + 1;
                            el.setAttribute('data-niva-id', nid);
                            
                            var sel = '';
                            var txt = (el.innerText || el.value || '').trim();
                            
                            if (el.id) sel = '#' + el.id;
                            else if (el.name) sel = el.tagName.toLowerCase() + '[name="' + el.name + '"]';
                            else if (el.placeholder) sel = el.tagName.toLowerCase() + '[placeholder="' + el.placeholder + '"]';
                            else if ((el.tagName === 'A' || el.tagName === 'BUTTON') && txt) sel = el.tagName.toLowerCase() + ':text("' + txt.slice(0, 20) + '")';
                            else sel = '[data-niva-id="' + nid + '"]';

                            items.push({
                                nid: nid,
                                selector: sel,
                                tag: el.tagName.toLowerCase(),
                                type: el.type || '',
                                name: el.name || '',
                                placeholder: el.getAttribute('placeholder') || '',
                                text: txt.slice(0, 40),
                                checked: el.checked || false,
                                disabled: el.disabled || false
                            });
                        }
                        return JSON.stringify(items);
                    } catch (e) { return JSON.stringify({error: e.message}); }
                }"""
                map_res = await mcp_realm.execute("chrome-devtools:evaluate_script", {"function": js_map})
                raw_map = parse_val(map_res)
                if isinstance(raw_map, str):
                    try: 
                        loaded = json.loads(raw_map)
                        interactive_map = loaded if isinstance(loaded, list) else []
                    except: interactive_map = []
                else:
                    interactive_map = raw_map if isinstance(raw_map, list) else []

                # NATIVE ERROR DETECTION (Discovery Mode)
                err_text = ""
                try:
                    # Trying a likely tool name
                    console_res = await mcp_realm.execute("chrome-devtools:list_console_messages", {}) 
                    native_logs = str(parse_val(console_res))
                    if "error" in native_logs.lower():
                         err_text += f"\n[CONSOLE ERRORS]: {native_logs[:500]}"
                except Exception as e:
                    # In discovery mode, we log the error to see available tools/args
                    logger.warning(f"[DISCOVERY] Tool call failed: {e}")
                
                # Manual fallback 
                js_semantic = "() => { const text = document.body.innerText.slice(0, 5000); const inputs = Array.from(document.querySelectorAll('input')).map(i => (i.name || i.placeholder || 'input') + ': ' + i.value).join(' | '); return JSON.stringify({ inputs: inputs, text: text }); }"
                semantic_res = await mcp_realm.execute("chrome-devtools:evaluate_script", {"function": js_semantic})
                sem_data = parse_val(semantic_res)
                if isinstance(sem_data, str):
                    try: sem_data = json.loads(sem_data)
                    except: sem_data = {"text": sem_data}
                
                if err_text: logger.debug(f"NATIVE ERRORS: {err_text}")

                semantic_text = f"URL: {current_url}\nTITLE: {current_title}\nERRORS: {err_text}\nINPUTS: {sem_data.get('inputs')}\nCONTENT:\n{sem_data.get('text')}"

                return current_url, current_title, semantic_text, interactive_map
            except Exception as e:
                logger.warning(f"[BROWSER_MCP] state failed: {e}")
                return "unknown", "unknown", "", []

        async def execute_action_batch(batch: list[dict]):
            for action in batch:
                a_type = action.get("type", "").lower()
                sel = action.get("selector")
                val = action.get("value", "")
                try:
                    if a_type == "click" and sel:
                        if ":text(" in sel: # Handle pseudo-text selector
                            text = re.search(r':text\("(.*?)"\)', sel).group(1)
                            # Robust text matching
                            js_click = "() => { const el = Array.from(document.querySelectorAll('a, button')).find(e => e.innerText && e.innerText.includes('" + text + "')); if(el) el.click(); }"
                            await mcp_realm.execute("chrome-devtools:evaluate_script", {"function": js_click})
                        else:
                            await mcp_realm.execute("chrome-devtools:click", {"selector": sel})
                        await asyncio.sleep(2.0)
                    elif a_type == "fill" and sel:
                        # React Native Value Setter Hack
                        safe_sel = sel.replace("'", "\\'").replace('"', '\\"')
                        safe_val = str(val).replace("'", "\\'").replace('"', '\\"')
                        
                        js_react_hack = "() => { " + \
                            "const element = document.querySelector('" + safe_sel + "'); " + \
                            "if (element) { " + \
                            "  const valueSetter = Object.getOwnPropertyDescriptor(element, 'value').set; " + \
                            "  const prototype = Object.getPrototypeOf(element); " + \
                            "  const prototypeValueSetter = Object.getOwnPropertyDescriptor(prototype, 'value').set; " + \
                            "  if (valueSetter && valueSetter !== prototypeValueSetter) { " + \
                            "    prototypeValueSetter.call(element, '" + safe_val + "'); " + \
                            "  } else { " + \
                            "    valueSetter.call(element, '" + safe_val + "'); " + \
                            "  } " + \
                            "  element.dispatchEvent(new Event('input', { bubbles: true })); " + \
                            "  element.dispatchEvent(new Event('change', { bubbles: true })); " + \
                            "  element.dispatchEvent(new Event('blur', { bubbles: true })); " + \
                            " return 'set'; " + \
                            "} return 'not_found'; }"
                        
                        await mcp_realm.execute("chrome-devtools:evaluate_script", {"function": js_react_hack})
                        
                        # Verification
                        js_v = "() => (document.querySelector('" + safe_sel + "') || {}).value"
                        v_res = await mcp_realm.execute("chrome-devtools:evaluate_script", {"function": js_v})
                        actual_val = parse_val(v_res)
                        if (str(val or '') == str(actual_val or '')):
                            pass # Silent success
                        else:
                            logger.debug(f"VERIFY FAIL: {sel} exp '{val}', got '{actual_val}'")
                    elif a_type == "navigate" and action.get("url"):
                        await mcp_realm.execute("chrome-devtools:navigate_page", {"url": action.get("url")})
                    elif a_type == "wait": await asyncio.sleep(float(action.get("seconds", 2)))
                except Exception as e: logger.warning(f"[BROWSER_MCP] {a_type} failed: {e}")
            try:
                shot = __import__('os').path.abspath(f"debug_step_{int(__import__('time').time())}.png")
                await mcp_realm.execute("chrome-devtools:take_screenshot", {"path": shot})
            except: pass

        if actions: # Scripted Mode
            await execute_action_batch(actions)
            return {"status": "success"}

        history = []
        final_result = {"status": "error", "message": "Incomplete"}
        initial_url = (re.search(r'https?://[^\s,]+', Task).group(0).rstrip('.') if re.search(r'https?://[^\s,]+', Task) else None)
        if initial_url:
            await mcp_realm.execute("chrome-devtools:navigate_page", {"url": initial_url})
            await asyncio.sleep(2)

        model = SharedModelProvider.get_model()
        p_registry = get_prompt_registry()
        
        for step in range(1, max_steps + 1):
            url, title, semantic_text, interaction = await capture_state_mcp()
            logger.info(f"STEP {step} - URL: {url} | MAP ITEMS: {len(interaction)}")
            
            grounding = "STRICT: Use selectors from the map. Prioritize semantic selectors like 'button:text(\"Sign up\")'."
            prompt = p_registry.get("capabilities.web.browser_driver",
                                   bot_name=settings.bot_name,
                                   current_url=url, page_title=title,
                                   semantic_snapshot=f"{semantic_text[:2000]}\n\n{grounding}",
                                   interactive_map=json.dumps(interaction, indent=2) if interaction else "None",
                                   history="\n".join(history[-5:]) or "Start.",
                                   goal=Task)
            
            response = await model.ainvoke(prompt)
            content = response.content if hasattr(response, 'content') else str(response)
            
            actions_data = extract_json(strip_thinking_tags(content))
            if not actions_data: continue
            actions_list = actions_data if isinstance(actions_data, list) else [actions_data]
            
            should_break = False
            for action in actions_list:
                if action.get("type", "").lower() == "finish":
                    final_result = {"status": "success", "message": action.get("summary", "Done")}
                    should_break = True
                    break
                await execute_action_batch([action])
                history.append(f"{action.get('type','').upper()}: {action.get('thought','')}")
            if should_break: break
        return final_result
    except Exception as e:
        logger.error(f"[BROWSER_MCP] Crash: {e}")
        return {"status": "error", "message": str(e)}