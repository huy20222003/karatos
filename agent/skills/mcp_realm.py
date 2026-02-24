"""
MCP Skill Realm
Enables integration with external tools via the Model Context Protocol (MCP).
"""
import asyncio
import json
import os
from typing import Any, Dict, List, Optional
from contextlib import AsyncExitStack

# mcp import
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.sse import sse_client
from utils.logger import get_logger

from .base import BaseSkillRealm
from config.settings import settings

logger = get_logger()

class MCPRealm(BaseSkillRealm):
    """
    Realm for interacting with MCP-compliant servers.
    Handles tool discovery and execution using the Model Context Protocol.
    Supports persistent sessions for stateful servers using AsyncExitStack.
    """
    
    def __init__(self):
        self.servers: Dict[str, StdioServerParameters] = {}
        # active_sessions stores: {server_name: {'session': ClientSession, 'stack': AsyncExitStack}}
        self.active_sessions: Dict[str, Dict[str, Any]] = {}
        self._initialized = False
        self._load_config()

    def _load_config(self):
        """Load MCP server configurations from settings"""
        server_configs = settings.mcp_servers
        for name, config in server_configs.items():
            try:
                env_vars = config.get("env", None)
                if env_vars:
                    # NGO FIX: Expand environment variables (e.g. ${API_KEY})
                    env_vars = {k: os.path.expandvars(v) for k, v in env_vars.items()}
                
                command = config.get("command")
                if command and (command.startswith("http://") or command.startswith("https://")):
                     self.servers[name] = command # Store URL directly
                else:
                    self.servers[name] = StdioServerParameters(
                        command=command,
                        args=config.get("args", []),
                        env=env_vars
                    )
                logger.info(f"[MCP] Configured server: {name}")
            except Exception as e:
                logger.error(f"[MCP] Failed to configure server {name}: {e}")

    async def _ensure_session(self, server_name: str) -> Optional[ClientSession]:
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
                # SSE Client
                logger.info(f"[MCP] Connecting to SSE server at: {params}")
                read, write = await stack.enter_async_context(sse_client(params))
            else:
                # Stdio Client
                logger.info(f"[MCP] Starting stdio client for: {server_name}")
                read, write = await stack.enter_async_context(stdio_client(params))
            
            # Enter session context
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
            except Exception as e:
                logger.warning(f"[MCP] Error closing session {server_name}: {e}")

    async def shutdown(self):
        """Close all active sessions."""
        for name in list(self.active_sessions.keys()):
            await self.close_session(name)

    async def list_tools(self) -> List[Dict[str, Any]]:
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
                # Invalidate session if listing fails
                await self.close_session(server_name)
                
        return all_tools

    async def execute(self, action: str, params: dict) -> Any:
        """
        Execute an MCP tool via a persistent session.
        Action format: 'server_name:tool_name'
        """
        try:
            # Strip 'mcp:' prefix if present
            if action.lower().startswith("mcp:"):
                action = action[4:]
                
            server_name = None
            tool_name = None

            if ":" not in action:
                # Optimized Map Lookup (Phase 21.1)
                if action.upper() in getattr(self, '_tool_map', {}):
                    server_name = self._tool_map[action.upper()]
                    tool_name = action.lower()
                    logger.debug(f"[MCP] Using cached server '{server_name}' for tool '{tool_name}'")
                else:
                    # Fallback: Search for the tool across all servers if server prefix is missing
                    logger.debug(f"[MCP] Action '{action}' missing server prefix. Searching...")
                    all_tools = await self.list_tools()
                    # list_tools returns tools as 'mcp:server:tool'
                    for t in all_tools:
                        tool_parts = t['name'].split(":")
                        if len(tool_parts) >= 3 and tool_parts[2].upper() == action.upper():
                            server_name = tool_parts[1]
                            tool_name = tool_parts[2]
                            # Update cache
                            if not hasattr(self, '_tool_map'): self._tool_map = {}
                            self._tool_map[tool_name.upper()] = server_name
                            logger.info(f"[MCP] Found tool {tool_name} on server {server_name}")
                            break
                    else:
                        return {"error": f"Invalid action format. Expected 'server:tool' and tool '{action}' not found."}
            else:
                s_part, t_part = action.split(":", 1)
                # Case-insensitive server lookup
                for s in self.servers:
                    if s.lower() == s_part.lower():
                        server_name = s
                        break
                else:
                    server_name = s_part # Fallback to original
                
                tool_name = t_part.lower() # Always lowercase tool names for MCP
            
            if server_name not in self.servers:
                return {"status": "error", "message": f"MCP Server '{server_name}' not configured"}
            
            # Ensure persistent session
            session = await self._ensure_session(server_name)
            if not session:
                 return {"status": "error", "message": f"Could not connect to MCP server '{server_name}'"}
            
            logger.info(f"[MCP] Executing {tool_name} on {server_name}...")
            result = await session.call_tool(tool_name, params)
            
            # Handle MCP tool result content
            content_list = []
            if hasattr(result, 'content'):
                for c in result.content:
                     if hasattr(c, 'text') and c.text:
                         content_list.append(c.text)
                     elif hasattr(c, 'type') and c.type == 'text':
                         content_list.append(c.text)
                     else:
                         # Handle Image/Binary content if needed, for now str()
                         content_list.append(str(c))
            
            final_content = "\n".join(content_list)
            
            # Try parsing JSON if applicable (e.g. from evaluate)
            try:
                stripped = final_content.strip()
                if (stripped.startswith("{") and stripped.endswith("}")) or \
                   (stripped.startswith("[") and stripped.endswith("]")):
                     import json
                     return {"status": "success", "result": json.loads(stripped), "raw": final_content}
            except: pass
            
            return {
                "status": "success",
                "result": {"value": final_content},
                "content": final_content
            }
            
        except Exception as e:
            logger.error(f"[MCP] Execution error ({action}): {e}")
            # Check if connection issue, invalidate session
            if "pipe" in str(e).lower() or "connection" in str(e).lower() or "closed" in str(e).lower():
                 await self.close_session(server_name)
            return {"status": "error", "message": str(e)}

    async def get_bot_registrations(self) -> Dict[str, str]:
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


# Singleton helper for the registry
_mcp_realm = None

def get_mcp_realm():
    global _mcp_realm
    if _mcp_realm is None:
        _mcp_realm = MCPRealm()
    return _mcp_realm
