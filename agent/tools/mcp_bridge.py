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
    "class_name": "MCPBridge",
    "description": "MCP Protocol Bridge: Connects to external MCP-compliant servers for tool discovery and execution (e.g., mailbox, google_search, browser automation).",
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
        self._load_config()

    def _load_config(self):
        """Load MCP server configurations from settings"""
        server_configs = settings.mcp_servers
        for name, config in server_configs.items():
            try:
                env_vars = config.get("env", None)
                if env_vars:
                    env_vars = {k: os.path.expandvars(v) for k, v in env_vars.items()}
                
                command = config.get("command")
                if command and (command.startswith("http://") or command.startswith("https://")):
                     self.servers[name] = command
                else:
                    self.servers[name] = StdioServerParameters(
                        command=command,
                        args=config.get("args", []),
                        env=env_vars
                    )
                logger.info(f"[MCP] Configured server: {name}")
            except Exception as e:
                logger.error(f"[MCP] Failed to configure server {name}: {e}")

    async def _ensure_session(self, server_name: str) -> typing.Optional[ClientSession]:
        """Establish or retrieve a persistent session for an MCP server"""
        if server_name in self.active_sessions:
            return self.active_sessions[server_name]['session']
            
        if server_name not in self.servers:
            logger.error(f"[MCP] Server {server_name} not found in configuration")
            return None
            
        try:
            logger.info(f"[MCP] Starting persistent session for: {server_name}")
            stack = AsyncExitStack()
            params = self.servers[server_name]
            
            if isinstance(params, str) and (params.startswith("http://") or params.startswith("https://")):
                headers = {}
                if server_name.lower() == "mailbox":
                    headers = {"X-Mailbox-Token": settings.mailbox_auth_token}
                    logger.info(f"[MCP] Attaching X-Mailbox-Token for {server_name}")
                
                logger.info(f"[MCP] Connecting to SSE server at: {params}")
                read, write = await stack.enter_async_context(sse_client(params, headers=headers))
            else:
                logger.info(f"[MCP] Starting stdio client for: {server_name}")
                read, write = await stack.enter_async_context(stdio_client(params))
            
            session = await stack.enter_async_context(ClientSession(read, write))
            await session.initialize()
            
            self.active_sessions[server_name] = {
                'session': session,
                'stack': stack
            }
            logger.info(f"[MCP] Session established for: {server_name}")
            return session
            
        except Exception as e:
            logger.error(f"[MCP] Failed to start session for {server_name}: {e}")
            return None

    async def close_session(self, server_name: str):
        """Close a specific server session."""
        if server_name in self.active_sessions:
            logger.info(f"[MCP] Closing session: {server_name}")
            data = self.active_sessions.pop(server_name)
            try:
                await data['stack'].aclose()
            except RuntimeError as re:
                if "cancel scope" in str(re):
                    logger.debug(f"[MCP] Cancel scope mismatch for {server_name} during closure (expected on task mismatch)")
                else:
                    logger.warning(f"[MCP] Error closing session {server_name}: {re}")
            except Exception as e:
                logger.warning(f"[MCP] Error closing session {server_name}: {e}")

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
        Execute an MCP tool via a persistent session.
        Action format: 'server_name:tool_name' or 'mcp:server_name:tool_name'
        """
        try:
            if action.lower().startswith("mcp:"):
                action = action[4:]
                
            server_name = None
            tool_name = None

            if ":" not in action:
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

    async def get_bot_registrations(self) -> typing.Dict[str, str]:
        """Fetch and parse bot name-to-username registrations from mailbox."""
        try:
            response = await self.execute("mailbox:get_registrations", {})
            if response and response.get("status") == "success":
                res_box = response.get("result", {})
                if isinstance(res_box, dict) and "value" in res_box:
                    return json.loads(res_box["value"])
                elif isinstance(res_box, str):
                    return json.loads(res_box)
                elif isinstance(res_box, dict):
                    return res_box
        except Exception as e:
            logger.debug(f"[MCP] Failed to fetch bot registrations: {e}")
        return {}


# Singleton
_mcp_bridge = None

def get_mcp_bridge():
    global _mcp_bridge
    if _mcp_bridge is None:
        _mcp_bridge = MCPBridge()
    return _mcp_bridge
