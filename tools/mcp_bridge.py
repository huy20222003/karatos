"""
MCP Bridge Tool
Enables integration with external tools via the Model Context Protocol (MCP).
Extracted from skills/realms/mcp.py for realm-free architecture.
"""
from __future__ import annotations
import asyncio
import json
import os
import typing
from typing import Any, Dict, List, Optional, Union
from contextlib import AsyncExitStack

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.sse import sse_client
from utils.logger import get_logger
from config.settings import settings

logger = get_logger()

# Tool metadata for ToolRegistry auto-discovery
TOOL_META = {
    "name": "mcp_bridge",
    "aliases": ["mcp", "mcp_execute"],
    "description": "Cross-Protocol Bridge: Integrates diverse MCP servers for tool execution. Supports decentralized agent-to-agent (bot-to-bot) communication via networked mailboxes.",
    "author": "Karatos Core",
    "version": "1.0.0",
    "enabled": True,
    "class_name": "MCPBridge",
    "actions": [
        {
            "name": "mcp_execute",
            "description": "Execute a tool on an MCP server. Format: 'server_name:tool_name'.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {"type": "string", "description": "MCP action in 'server:tool' format."},
                    "params": {"type": "object", "description": "Parameters for the MCP tool."}
                },
                "required": ["action"]
            }
        }
    ]
}


class MCPBridge:
    """
    Bridge for interacting with MCP-compliant servers.
    Handles tool discovery and execution using the Model Context Protocol.
    Supports persistent sessions for stateful servers using AsyncExitStack.
    """
    
    def __init__(self):
        self.servers: typing.Dict[str, Any] = {}
        self.active_sessions: typing.Dict[str, typing.Dict[str, typing.Any]] = {}
        self._tool_map: typing.Dict[str, str] = {}
        self._initialized = False
        self.reload()

    def get_config_path(self) -> str:
        """Get the absolute path to the MCP configuration file"""
        from pathlib import Path
        config_path = Path(settings.mcp_config_path)
        if not config_path.is_absolute():
            root_dir = Path(__file__).parent.parent
            config_path = root_dir / settings.mcp_config_path
        return str(config_path.absolute())

    def reload(self):
        """Reload configuration from disk and refresh sessions if needed"""
        logger.info("[MCP] Reloading configuration from disk...")
        # We don't necessarily want to shut down ALL sessions immediately 
        # as it might interrupt ongoing tasks, but we need to refresh the server list.
        # However, for a clean reload when a server is edited/removed, shutdown is safer.
        self.servers.clear()
        self._load_config_from_json()
        logger.info(f"[MCP] Reload complete. {len(self.servers)} servers configured.")

    def _load_config_from_json(self):
        """Load MCP server configurations directly from JSON file"""
        from pathlib import Path
        config_path = Path(settings.mcp_config_path)
        if not config_path.is_absolute():
            # Try relative to the app root
            root_dir = Path(__file__).parent.parent
            config_path = root_dir / settings.mcp_config_path

        if config_path.exists():
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    external_config = json.load(f)
                    
                    # Support both key formats
                    json_servers = external_config.get("mcp_servers") or external_config.get("mcpServers")
                    if json_servers is None:
                        json_servers = external_config if isinstance(external_config, dict) else {}

                    for name, config in json_servers.items():
                        self.register_server(name, config)
                            
            except Exception as e:
                logger.warning(f"[MCP] Failed to load config from {config_path}: {e}")

    def register_server(self, name: str, config: dict):
        """Register a server configuration in memory"""
        try:
            env_vars = config.get("env", None)
            if env_vars:
                from dotenv import load_dotenv
                load_dotenv()
                env_vars = {k: os.path.expandvars(str(v)) for k, v in env_vars.items()}
            
            command = config.get("command")
            if command and (command.startswith("http://") or command.startswith("https://")):
                 self.servers[name] = command
            else:
                self.servers[name] = StdioServerParameters(
                    command=command,
                    args=config.get("args", []),
                    env=env_vars
                )
            logger.info(f"[MCP] Registered server: {name}")
        except Exception as e:
            logger.error(f"[MCP] Failed to register server {name}: {e}")

    def get_server_configs(self) -> dict:
        """Get the raw server configurations (for listing)"""
        # Re-read from file to ensure we're in sync with disk for management purposes
        from pathlib import Path
        config_path = Path(settings.mcp_config_path)
        if not config_path.is_absolute():
            root_dir = Path(__file__).parent.parent
            config_path = root_dir / settings.mcp_config_path
            
        if config_path.exists():
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return data.get("mcp_servers") or data.get("mcpServers") or (data if isinstance(data, dict) else {})
            except: pass
        return {}

    async def add_server(self, name: str, config: dict) -> bool:
        """Persist a new server to JSON and register it in memory"""
        from pathlib import Path
        config_path = Path(settings.mcp_config_path)
        if not config_path.is_absolute():
            root_dir = Path(__file__).parent.parent
            config_path = root_dir / settings.mcp_config_path
            
        try:
            # 1. Load existing
            data = {}
            if config_path.exists():
                with open(config_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            
            # 2. Determine key
            key = "mcpServers" if "mcpServers" in data else "mcp_servers"
            if key not in data and not isinstance(data, dict):
                data = {key: {}}
            elif key not in data:
                data[key] = {}
                
            # 3. Update
            data[key][name] = config
            
            # 4. Save
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4)
                
            # 5. Register in current Bridge instance
            self.register_server(name, config)
            return True
        except Exception as e:
            logger.error(f"[MCP] Failed to add server {name}: {e}")
            return False

    async def remove_server(self, name: str) -> bool:
        """Remove a server from JSON and memory"""
        from pathlib import Path
        config_path = Path(settings.mcp_config_path)
        if not config_path.is_absolute():
            root_dir = Path(__file__).parent.parent
            config_path = root_dir / settings.mcp_config_path
            
        try:
            if config_path.exists():
                with open(config_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                
                key = "mcpServers" if "mcpServers" in data else "mcp_servers"
                if key in data and name in data[key]:
                    del data[key][name]
                    with open(config_path, "w", encoding="utf-8") as f:
                        json.dump(data, f, indent=4)
                    
                    # Remove from memory
                    self.servers.pop(name, None)
                    await self.close_session(name)
                    return True
            return False
        except Exception as e:
            logger.error(f"[MCP] Failed to remove server {name}: {e}")
            return False

    async def _ensure_session(self, server_name: str) -> typing.Optional[ClientSession]:
        """Establish or retrieve a persistent session for an MCP server"""
        if server_name in self.active_sessions and 'session' in self.active_sessions[server_name]:
            return self.active_sessions[server_name]['session']
            
        if server_name not in self.servers:
            logger.error(f"[MCP] Server {server_name} not found in configuration")
            return None
            
        # Initialize placeholders to prevent concurrent identical startups
        ready_event = asyncio.Event()
        error_container = {}
        close_event = asyncio.Event()
        
        self.active_sessions[server_name] = {
            'close_event': close_event
        }
        
        logger.info(f"[MCP] Activating background session task for: {server_name}")
        task = asyncio.create_task(
            self._session_task(server_name, self.servers[server_name], ready_event, error_container),
            name=f"MCP_Session_{server_name}"
        )
        self.active_sessions[server_name]['task'] = task
        
        await ready_event.wait()
        
        if 'error' in error_container:
            logger.error(f"[MCP] Failed to start session for {server_name}: {error_container['error']}")
            self.active_sessions.pop(server_name, None)
            return None
            
        return self.active_sessions[server_name].get('session')

    async def _session_task(self, server_name: str, params: typing.Any, ready_event: asyncio.Event, error_container: dict):
        """Background task to inherently bind the anyio CancelScope to a single task."""
        try:
            if isinstance(params, str) and (params.startswith("http://") or params.startswith("https://")):
                headers = {}
                raw_config = self.get_server_configs().get(server_name, {})
                env_vars = raw_config.get("env", {})
                if env_vars:
                    from dotenv import load_dotenv
                    load_dotenv()
                    headers.update({k: os.path.expandvars(str(v)) for k, v in env_vars.items()})
                    
                async with sse_client(params, headers=headers, timeout=15.0, sse_read_timeout=600.0) as (read, write):
                    async with ClientSession(read, write) as session:
                        await session.initialize()
                        if server_name in self.active_sessions:
                            self.active_sessions[server_name]['session'] = session
                        ready_event.set()
                        logger.info(f"[MCP] Session established for: {server_name}")
                        
                        # Hold the context manager open until we need to close
                        close_event = self.active_sessions.get(server_name, {}).get('close_event')
                        if close_event:
                            await close_event.wait()
            else:
                async with stdio_client(params) as (read, write):
                    async with ClientSession(read, write) as session:
                        await session.initialize()
                        if server_name in self.active_sessions:
                            self.active_sessions[server_name]['session'] = session
                        ready_event.set()
                        logger.info(f"[MCP] Session established for: {server_name}")
                        
                        close_event = self.active_sessions.get(server_name, {}).get('close_event')
                        if close_event:
                            await close_event.wait()
                            
        except Exception as e:
            error_msg = str(e)
            if hasattr(e, "exceptions"):
                sub_msgs = [str(sub) for sub in e.exceptions]
                error_msg = f"{error_msg} -> " + ", ".join(sub_msgs)
                
            if not ready_event.is_set():
                error_container['error'] = error_msg
                ready_event.set()
            else:
                logger.debug(f"[MCP] Session task for {server_name} ended: {error_msg}")
        finally:
            if server_name in self.active_sessions:
                # Optionally clean up if this task exits unexpectedly
                # We do not pop here completely aggressively to avoid race conditions,
                # but removing 'session' forces a reconnect next time.
                self.active_sessions.get(server_name, {}).pop('session', None)

    async def close_session(self, server_name: str):
        """Close a specific server session."""
        if server_name in self.active_sessions:
            logger.info(f"[MCP] Closing session: {server_name}")
            data = self.active_sessions.pop(server_name)
            if 'close_event' in data:
                data['close_event'].set()
            # Task will gracefully exit its async with blocks

    async def shutdown(self):
        """Close all active sessions."""
        for name in list(self.active_sessions.keys()):
            await self.close_session(name)

    async def list_tools(self) -> typing.List[typing.Dict[str, typing.Any]]:
        """Discover all tools across all configured MCP servers"""
        all_tools = []
        for server_name in self.servers:
            try:
                session = await self._ensure_session(server_name)
                if not session: continue
                
                tools_result = await session.list_tools()
                for tool in tools_result.tools:
                    tool_data = {
                        "name": f"mcp:{server_name}:{tool.name}",
                        "description": tool.description,
                        "input_schema": tool.inputSchema,
                        "server": server_name
                    }
                    all_tools.append(tool_data)
            except Exception as e:
                logger.error(f"[MCP] Failed to list tools for {server_name}: {e}")
                await self.close_session(server_name)
                
        return all_tools

    async def execute(self, action: str, params: dict) -> typing.Any:
        """
        Execute an MCP tool or Agent action.
        Agent format: 'agent:name:tool' (e.g. 'agent:niva_sentry:receive_message')
        """
        try:
            if action.startswith("mcp:"):
                action = action[4:]
                
            server_name = None
            tool_name = None

            if ":" not in action:
                # Direct tool lookup
                if action.upper() in self._tool_map:
                    server_name = self._tool_map[action.upper()]
                    tool_name = action.lower()
                else:
                    logger.debug(f"[MCP] Action '{action}' missing server prefix. Searching...")
                    all_tools = await self.list_tools()
                    for t in all_tools:
                        tool_parts = t['name'].split(":")
                        if len(tool_parts) >= 3 and tool_parts[2].upper() == action.upper():
                            server_name = tool_parts[1]
                            tool_name = tool_parts[2]
                            self._tool_map[tool_name.upper()] = server_name
                            logger.info(f"[MCP] Found tool {tool_name} on server {server_name}")
                            break
                    else:
                        return {"error": f"Invalid action format. Expected 'server:tool' and tool '{action}' not found."}
            else:
                s_part, t_part = action.split(":", 1)
                for s in self.servers:
                    if s.lower() == s_part.lower():
                        server_name = s
                        break
                else:
                    server_name = s_part
                
                tool_name = t_part.lower()
            
            if server_name not in self.servers:
                return {"status": "error", "message": f"MCP Server '{server_name}' not configured"}
            
            session = await self._ensure_session(server_name)
            if not session:
                 return {"status": "error", "message": f"Could not connect to MCP server '{server_name}'"}
            
            logger.info(f"[MCP] Executing {tool_name} on {server_name}...")
            result = await session.call_tool(tool_name, params)
            
            content_list = []
            if hasattr(result, 'content'):
                for c in result.content:
                     if hasattr(c, 'text') and c.text:
                         content_list.append(c.text)
                     elif hasattr(c, 'type') and c.type == 'text':
                         content_list.append(c.text)
                     else:
                         content_list.append(str(c))
            
            final_content = "\n".join(content_list)
            
            try:
                stripped = final_content.strip()
                if (stripped.startswith("{") and stripped.endswith("}")) or \
                   (stripped.startswith("[") and stripped.endswith("]")):
                     return {"status": "success", "result": json.loads(stripped), "raw": final_content}
            except: pass
            
            return {
                "status": "success",
                "result": {"value": final_content},
                "content": final_content
            }
            
        except Exception as e:
            logger.error(f"[MCP] Execution error ({action}): {e}")
            if "pipe" in str(e).lower() or "connection" in str(e).lower() or "closed" in str(e).lower():
                 await self.close_session(server_name)
            return {"status": "error", "message": str(e)}



# Singleton
_mcp_bridge = None

def get_mcp_bridge():
    global _mcp_bridge
    if _mcp_bridge is None:
        _mcp_bridge = MCPBridge()
    return _mcp_bridge
