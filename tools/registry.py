"""
Tool Registry — Dynamic dispatch hub for all tools.
Auto-discovers tools from the tools/ folder via TOOL_META convention.
Builds a dispatch map from aliases so adding a new tool requires ZERO changes here.

How it works:
  1. On init, scans tools/*.py for TOOL_META
  2. Each TOOL_META defines: name, aliases, class_name, actions
  3. Builds a flat alias→handler map: {"bash": ShellExecutor, "sql": DatabaseDynamic, ...}
  4. dispatch() just looks up the alias and calls handler.execute(**params)

To add a new tool:
  - Create tools/my_tool.py with TOOL_META (including "aliases" and "class_name")
  - Add a class with async execute(**params) method
  - Done — no changes to this file needed.
"""
import os
import importlib
import inspect
import asyncio
from typing import Any, Dict, List, Optional
from utils.logger import get_logger

logger = get_logger()


class ToolRegistry:
    """
    Central registry for all executable tools.
    Auto-discovers tools and builds a dynamic dispatch map from aliases.
    """
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ToolRegistry, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        
        self.tools_root = os.path.dirname(__file__)
        self.tools: Dict[str, Dict[str, Any]] = {}  # tool_name -> {meta, module, handler_class}
        self._dispatch_map: Dict[str, Dict[str, Any]] = {}  # alias -> {handler, meta, tool_name}
        self._mcp_bridge = None
        self._load_tools()
        self._build_dispatch_map()
        self._initialized = True
        logger.info(f"ToolRegistry initialized with {len(self.tools)} tools, {len(self._dispatch_map)} aliases.")

    # ──────────────────────────────────────────────
    # DISCOVERY
    # ──────────────────────────────────────────────

    def _load_tools(self):
        """Auto-discover tools by scanning for TOOL_META in tool modules."""
        skip_files = {"__init__.py", "registry.py"}
        
        for filename in sorted(os.listdir(self.tools_root)):
            if not filename.endswith(".py") or filename in skip_files:
                continue
            
            module_name = filename[:-3]
            try:
                module = importlib.import_module(f"tools.{module_name}")
                meta = getattr(module, "TOOL_META", None)
                
                if meta and isinstance(meta, dict):
                    # Check if tool is enabled
                    if not meta.get("enabled", False):
                        logger.info(f"[ToolRegistry] Skipping disabled tool: {module_name}")
                        continue

                    tool_name = meta.get("name", module_name)
                    
                    # Find the handler class (class with execute method)
                    handler_class = self._find_handler_class(module, meta)
                    
                    self.tools[tool_name] = {
                        "meta": meta,
                        "module": module,
                        "module_name": module_name,
                        "handler_class": handler_class,
                    }
                    logger.debug(f"[ToolRegistry] Loaded: {tool_name} → {handler_class.__name__ if handler_class else 'NO_HANDLER'}")
                else:
                    logger.debug(f"[ToolRegistry] Skipped {module_name} (no TOOL_META)")
                    
            except Exception as e:
                logger.warning(f"[ToolRegistry] Failed to load '{module_name}': {e}")

    @staticmethod
    def _find_handler_class(module, meta: dict):
        """
        Find the handler class in a module. Resolution order:
        1. meta["class_name"] if specified
        2. First class with an 'execute' method
        3. First async function named 'execute'
        """
        # 1. Explicit class_name in meta
        class_name = meta.get("class_name")
        if class_name:
            cls = getattr(module, class_name, None)
            if cls:
                return cls

        # 2. Auto-detect class with execute
        for attr_name in dir(module):
            obj = getattr(module, attr_name)
            if (inspect.isclass(obj) and 
                hasattr(obj, "execute") and 
                attr_name != "object" and
                not attr_name.startswith("_")):
                return obj
        
        # 3. Module-level async function (e.g., search_web)
        for attr_name in dir(module):
            obj = getattr(module, attr_name)
            if inspect.iscoroutinefunction(obj) and not attr_name.startswith("_"):
                # Wrap in a fake class for uniform dispatch
                return _wrap_function_as_handler(obj, attr_name)
        
        return None

    def _build_dispatch_map(self):
        """
        Build a flat alias→handler map from all loaded TOOL_META.
        Each tool contributes: its name, its aliases, and its action names.
        """
        for tool_name, tool_data in self.tools.items():
            meta = tool_data["meta"]
            handler = tool_data["handler_class"]
            
            if not handler:
                logger.warning(f"[ToolRegistry] Tool '{tool_name}' has no handler class. Skipping dispatch registration.")
                continue

            # Collect all aliases for this tool
            all_aliases = set()
            
            # 1. Tool name itself
            all_aliases.add(tool_name.lower())
            
            # 2. Explicit aliases from meta
            for alias in meta.get("aliases", []):
                all_aliases.add(alias.lower())
            
            # 3. Action names from meta.actions
            for action in meta.get("actions", []):
                action_name = action.get("name", "")
                if action_name:
                    all_aliases.add(action_name.lower())
            
            # Register all aliases
            for alias in all_aliases:
                if alias in self._dispatch_map:
                    existing = self._dispatch_map[alias]["tool_name"]
                    logger.warning(f"[ToolRegistry] Alias conflict: '{alias}' → {existing} vs {tool_name}. Keeping {existing}.")
                else:
                    self._dispatch_map[alias] = {
                        "handler": handler,
                        "meta": meta,
                        "tool_name": tool_name,
                    }

    # ──────────────────────────────────────────────
    # DISPATCH
    # ──────────────────────────────────────────────

    def get_mcp_bridge(self):
        """Lazy-load the MCP bridge."""
        if self._mcp_bridge is None:
            try:
                from tools.mcp_bridge import get_mcp_bridge
                self._mcp_bridge = get_mcp_bridge()
            except Exception as e:
                logger.error(f"[ToolRegistry] Failed to load MCP bridge: {e}")
        return self._mcp_bridge

    async def dispatch(self, action_name: str, params: dict = None) -> Any:
        """
        Dispatch an action to the appropriate tool.
        
        Resolution order:
        1. Alias lookup in dispatch map (built from TOOL_META.aliases + action names)
        2. MCP bridge (for 'mcp:server:tool' or 'server:tool' format)
        3. Fuzzy fallback via generic tool scan
        """
        if params is None:
            params = {}

        clean_action = action_name.lower().strip()
        
        # Filter out internal metadata from params
        internal_keys = {"os_platform", "speculative_data_context"}
        clean_params = {k: v for k, v in params.items() if k not in internal_keys}

        # ─── 1. DYNAMIC DISPATCH via alias map ───
        if clean_action in self._dispatch_map:
            entry = self._dispatch_map[clean_action]
            handler = entry["handler"]
            tool_name = entry["tool_name"]
            
            logger.info(f"[ToolRegistry] Dispatching '{clean_action}' → {tool_name}")
            
            try:
                # Pass action name to tools that need it for internal routing
                # (e.g., process_monitor routes system_info/list_processes/check_port)
                clean_params["_dispatched_action"] = clean_action
                
                return await self._invoke_handler(handler, clean_params)
            except Exception as e:
                logger.error(f"[ToolRegistry] Dispatch error for '{clean_action}': {e}")
                return {"status": "error", "message": f"Tool execution failed: {str(e)}"}


        # ─── 3. MCP BRIDGE (for mcp:server:tool format) ───
        if ":" in clean_action:
            bridge = self.get_mcp_bridge()
            if bridge:
                return await bridge.execute(clean_action, clean_params)
            return {"status": "error", "message": "MCP Bridge not available."}

        # ─── 3. FALLBACK: MCP last resort ───
        bridge = self.get_mcp_bridge()
        if bridge:
            return await bridge.execute(action_name, clean_params)

        return {"status": "error", "message": f"No tool found for action '{action_name}'. Available: {', '.join(sorted(self._dispatch_map.keys())[:20])}"}

    async def _invoke_handler(self, handler, params: dict) -> Any:
        """
        Invoke a handler's execute method uniformly.
        Handles both class methods and wrapped functions.
        """
        # Get the internal routing key
        dispatched_action = params.get("_dispatched_action", "")
        
        # Check if handler needs instantiation
        if inspect.isclass(handler):
            execute_method = getattr(handler, "execute", None)
            if not execute_method:
                # If wrapped function class
                execute_method = handler.execute
        else:
            execute_method = handler if callable(handler) else getattr(handler, "execute", None)

        if not execute_method or not callable(execute_method):
            return {"status": "error", "message": f"Handler {handler} has no callable execute method."}

        try:
            sig = inspect.signature(execute_method)
            has_kwargs = any(p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values())
            
            # Build target params
            target_params = {}
            for name, value in params.items():
                if name in sig.parameters or has_kwargs:
                    target_params[name] = value
            
            # Special logic for routing information: 
            # If tool expects 'action' but it's not in params (or is empty), 
            # fill it with dispatched_action
            if "action" in sig.parameters and not target_params.get("action"):
                target_params["action"] = dispatched_action

            # Final check: if 'action' is a required positional argument but missing, 
            # we MUST provide it to avoid TypeError
            param_list = list(sig.parameters.values())
            # Skip 'self' or 'cls' for bound methods
            if inspect.ismethod(execute_method):
                param_list = param_list # inspect.signature already excludes 'self'/'cls' for bound methods
            
            # Check for missing required positional args
            for p in param_list:
                if p.name == "action" and p.default == inspect.Parameter.empty and "action" not in target_params:
                    target_params["action"] = dispatched_action

            # Determine whether to call as class/static or instance
            is_bound = inspect.ismethod(execute_method)
            
            if inspect.isclass(handler) and not is_bound:
                if isinstance(inspect.getattr_static(handler, "execute"), (classmethod, staticmethod)):
                    return await execute_method(**target_params)
                else:
                    instance = handler()
                    return await instance.execute(**target_params)
            
            return await execute_method(**target_params)

        except Exception as e:
            logger.error(f"[ToolRegistry] Execution failed in handler: {e}")
            raise

    # ──────────────────────────────────────────────
    # SCHEMA & CAPABILITY QUERIES
    # ──────────────────────────────────────────────

    def list_tools(self) -> List[Dict[str, Any]]:
        """Return tool schemas for the Brain/Planner."""
        schemas = []
        # Calculate root one level above tools/
        project_root = os.path.dirname(self.tools_root)
        
        for name, tool_data in self.tools.items():
            meta = tool_data["meta"]
            module = tool_data["module"]
            actions = meta.get("actions", [])
            aliases = meta.get("aliases", [])
            
            # Calculate location relative to project root
            try:
                abs_path = getattr(module, "__file__", "")
                rel_path = os.path.relpath(abs_path, project_root) if abs_path else "dynamic"
            except:
                rel_path = "dynamic"

            if actions:
                for action in actions:
                    schemas.append({
                        "name": action.get("name", name),
                        "description": action.get("description", meta.get("description", "")),
                        "parameters": action.get("parameters", action.get("input_schema", {})),
                        "tool_source": name,
                        "location": rel_path,
                        "aliases": aliases,
                    })
            else:
                schemas.append({
                    "name": name,
                    "description": meta.get("description", ""),
                    "parameters": meta.get("parameters", {}),
                    "location": rel_path,
                    "aliases": aliases,
                })
        return schemas

    def get_tool_summaries(self) -> str:
        """Return compact name:description pairs for capability scanning."""
        lines = []
        project_root = os.path.dirname(self.tools_root)
        
        for name, tool_data in self.tools.items():
            meta = tool_data["meta"]
            module = tool_data["module"]
            aliases = meta.get("aliases", [])
            alias_str = f" (aliases: {', '.join(aliases)})" if aliases else ""
            
            try:
                abs_path = getattr(module, "__file__", "")
                rel_path = os.path.relpath(abs_path, project_root) if abs_path else "dynamic"
            except:
                rel_path = "dynamic"
                
            lines.append(f"- {meta.get('name', name)}{alias_str}: {meta.get('description', 'No description')} (location: {rel_path})")
        return "\n".join(lines)

    async def get_tool_schemas(self) -> List[Dict[str, Any]]:
        """Unified schema collection for planner compatibility."""
        schemas = self.list_tools()
        
        bridge = self.get_mcp_bridge()
        if bridge:
            # 1. MCP Standard Tools
            try:
                mcp_tools = await bridge.list_tools()
                for t in mcp_tools:
                    p = t.pop("input_schema", {})
                    if p and "properties" not in p and isinstance(p, dict):
                        p = {"type": "object", "properties": p}
                    t["parameters"] = p
                    schemas.append(t)
            except Exception as e:
                logger.warning(f"[ToolRegistry] Failed to fetch MCP tools: {e}")
            
        
        return schemas

    def get_capabilities_map(self) -> Dict[str, Dict[str, str]]:
        """Return a capabilities map: {tool_name: {description, actions}}.
        Used by skill_generator to auto-populate required_capabilities."""
        caps = {}
        for name, tool_data in self.tools.items():
            meta = tool_data["meta"]
            actions = meta.get("actions", [])
            action_names = [a.get("name", "") for a in actions]
            caps[name] = {
                "description": meta.get("description", ""),
                "actions": action_names,
            }
        return caps

    async def shutdown(self):
        """Shutdown all tool resources."""
        bridge = self.get_mcp_bridge()
        if bridge:
            await bridge.shutdown()
        logger.info("[ToolRegistry] Shutdown complete.")


# ──────────────────────────────────────────────
# HELPERS
# ──────────────────────────────────────────────

def _wrap_function_as_handler(func, name: str):
    """Wrap a standalone async function as a handler class for uniform dispatch."""
    class _FuncWrapper:
        @staticmethod
        async def execute(**params):
            return await func(**params)
    _FuncWrapper.__name__ = f"{name}_wrapper"
    return _FuncWrapper


# Singleton
_tool_registry = None

def get_tool_registry():
    global _tool_registry
    if _tool_registry is None:
        _tool_registry = ToolRegistry()
    return _tool_registry
