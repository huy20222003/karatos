import asyncio
import json
import re
from typing import Any, Optional, Dict, List
from utils.logger import get_logger
from config.settings import settings

logger = get_logger()

# Tool metadata for ToolRegistry auto-discovery
TOOL_META = {
    "name": "webmcp_bridge",
    "aliases": ["webmcp", "web_tool"],
    "class_name": "WebMCPBridge",
    "description": "WebMCP Bridge: Interacts with agent-aware websites using the Web Model Context Protocol. Discovers and calls structured tools exposed by web pages instead of using screen scraping.",
    "enabled": True,
    "author": "Karatos Core",
    "version": "1.0.0",
    "actions": [
        {
            "name": "navigate",
            "description": "Navigate to a URL and wait for the page to load.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "The URL to navigate to."}
                },
                "required": ["url"]
            }
        },
        {
            "name": "list_web_tools",
            "description": "Discover all WebMCP tools (Declarative and Imperative) on the current page.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        },
        {
            "name": "call_web_tool",
            "description": "Execute a WebMCP tool on the current page with specified arguments.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "The name of the tool to call."},
                    "arguments": {"type": "object", "description": "The arguments to pass to the tool."}
                },
                "required": ["name", "arguments"]
            }
        }
    ]
}

class WebMCPBridge:
    """Specialized tool for WebMCP interaction via Chrome DevTools MCP."""

    @classmethod
    async def execute(cls, action: str = "", **kwargs) -> Any:
        # Support both 'action' as positional/keyword and '_dispatched_action' from registry
        route = action or kwargs.get("_dispatched_action") or ""
        
        bridge = cls()
        if route == "navigate":
            return await bridge.navigate(kwargs.get("url"))
        elif route == "list_web_tools":
            return await bridge.list_web_tools()
        elif route == "call_web_tool":
            return await bridge.call_web_tool(kwargs.get("name"), kwargs.get("arguments"))
        else:
            return {"status": "error", "message": f"Unknown WebMCP action: {route or 'None'}"}

    def __init__(self):
        from tools.mcp_bridge import get_mcp_bridge
        self.mcp = get_mcp_bridge()
        if not self.mcp:
            raise RuntimeError("MCP Bridge not available. Ensure chrome-devtools-mcp is configured.")

    async def navigate(self, url: str) -> Dict:
        logger.info(f"[WebMCP] Navigating to {url}")
        res = await self.mcp.execute("chrome-devtools:navigate_page", {"url": url})
        await asyncio.sleep(3) # Wait for potential JS registration
        return res

    def _parse_mcp_result(self, res: Any) -> Any:
        """Standard extraction from MCP bridge responses."""
        if res is None: return None
        data = res
        if isinstance(res, dict):
            if "value" in res: data = res["value"]
            elif "result" in res:
                r = res["result"]
                data = r.get("value") if isinstance(r, dict) else r
            else: data = res.get("content") or str(res)
        
        if isinstance(data, str):
            # Handle Markdown JSON blocks
            match = re.search(r'```json\s*(.*?)\s*```', data, re.DOTALL)
            if match:
                js = match.group(1).strip()
                try: return json.loads(js)
                except: return js
            # Handle plain "returned:" legacy format
            if "returned:" in data:
                val_match = re.search(r'returned:\s*(.*)', data)
                if val_match:
                    v = val_match.group(1).strip()
                    try: return json.loads(v)
                    except: return v
        return data

    async def list_web_tools(self) -> Dict[str, Any]:
        """
        List discoverable WebMCP tools on the current page.
        Uses polyfill injection and deep JS analysis as a fallback.
        """
        logger.debug("[WebMCP] Scanning for web tools...")
        
        # 1. Inject WebMCP Polyfill
        js_polyfill = """() => {
            if (window.navigator.modelContext) return "already_exists";
            try {
                window.__karatos_webmcp_tools = window.__karatos_webmcp_tools || [];
                const context = {
                    registerTool: (tool) => {
                        console.log("WebMCP(Karatos): Registering tool", tool.name);
                        if (!window.__karatos_webmcp_tools.find(t => t.name === tool.name)) {
                            window.__karatos_webmcp_tools.push(tool);
                        }
                        return true;
                    },
                    listTools: () => window.__karatos_webmcp_tools
                };
                Object.defineProperty(window.navigator, 'modelContext', {
                    get: () => context,
                    configurable: true
                });
                return "injected";
            } catch (e) { return "error: " + e.message; }
        }"""
        
        await self.mcp.execute("chrome-devtools:evaluate_script", {"function": js_polyfill})
        await asyncio.sleep(2) 
        
        # 2. Main Scan (API & Declarative)
        js_discovery = """() => {
            const results = { imperative: [], declarative: [] };
            try {
                // Imperative
                const ctx = window.navigator.modelContext;
                if (ctx && ctx.listTools) {
                    const imp = ctx.listTools();
                    if (Array.isArray(imp)) results.imperative = imp;
                }
                // Declarative
                const forms = Array.from(document.querySelectorAll('form[toolname]'));
                results.declarative = forms.map(f => ({
                    name: f.getAttribute('toolname'),
                    description: f.getAttribute('description') || "Declarative Tool",
                    parameters: {},
                    discovery: 'declarative'
                }));
            } catch (e) {}
            return results;
        }"""
        
        disc_res = await self.mcp.execute("chrome-devtools:evaluate_script", {"function": js_discovery})
        parsed_res = self._parse_mcp_result(disc_res)
        
        tools = []
        if isinstance(parsed_res, dict):
            tools.extend(parsed_res.get("imperative", []))
            tools.extend(parsed_res.get("declarative", []))
            
        # 3. Deep Scan Fallback (Analyze JS source)
        if not tools:
            logger.info("[WebMCP] Standard scan found 0 tools. Attempting Deep Scan...")
            js_deep_scan = """async () => {
                const tools = [];
                const scripts = Array.from(document.querySelectorAll('script[src]'));
                for (const s of scripts) {
                    try {
                        const resp = await fetch(s.src);
                        const text = await resp.text();
                        // Look for name: "...", description: "..." patterns
                        const regex = /name\s*:\s*"([^"]+)"\s*,\s*description\s*:\s*"([^"]+)"/g;
                        let match;
                        while ((match = regex.exec(text)) !== null) {
                            tools.push({
                                name: match[1],
                                description: match[2],
                                parameters: {},
                                discovery: 'deep_scan'
                            });
                        }
                    } catch (e) {}
                }
                return tools;
            }"""
            deep_res = await self.mcp.execute("chrome-devtools:evaluate_script", {"function": js_deep_scan})
            tools = self._parse_mcp_result(deep_res) or []

        # Dedup and finalize
        seen = set()
        final_tools = []
        for t in tools:
            if isinstance(t, dict) and "name" in t:
                if t["name"] not in seen:
                    final_tools.append(t)
                    seen.add(t["name"])
        
        logger.info(f"[WebMCP] Discovered {len(final_tools)} tools.")
        return {"status": "success", "tools": final_tools, "count": len(final_tools)}

    async def call_web_tool(self, name: str, arguments: Dict) -> Dict:
        logger.info(f"[WebMCP] Calling web tool: {name} with args: {arguments}")
        
        # Inline arguments safely as JSON strings to avoid MCP parameter validation issues
        safe_name = json.dumps(name)
        safe_args = json.dumps(arguments)
        
        js_call = f"""async () => {{
            try {{
                const name = {safe_name};
                const args = {safe_args};
                
                // 1. Try Imperative
                if (window.navigator && window.navigator.modelContext && window.navigator.modelContext.callTool) {{
                    const tools = window.navigator.modelContext.listTools ? window.navigator.modelContext.listTools() : [];
                    if (tools.some(t => t.name === name)) {{
                        return await window.navigator.modelContext.callTool(name, args);
                    }}
                }}
                
                // 2. Try Declarative (Form Submission)
                const form = document.querySelector(`form[toolname="${{name}}"]`);
                if (form) {{
                    for (const [key, val] of Object.entries(args)) {{
                        const input = form.querySelector(`[name="${{key}}"]`);
                        if (input) input.value = val;
                    }}
                    form.submit();
                    return {{ status: "submitted", tool: name }};
                }}
                
                return {{ error: "Tool not found or WebMCP not supported" }};
            }} catch (e) {{ return {{ error: e.message }}; }}
        }}"""
        
        res = await self.mcp.execute("chrome-devtools:evaluate_script", {
            "function": js_call
        })
        
        return self._parse_mcp_result(res)
