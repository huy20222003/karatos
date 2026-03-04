from fastapi import APIRouter, HTTPException, Body
from typing import Dict, Any
from utils.logger import get_logger
from tools.mcp_bridge import get_mcp_bridge

router = APIRouter()
logger = get_logger()

@router.get("/list")
async def list_mcp_servers():
    """List all configured MCP servers and their status."""
    try:
        bridge = get_mcp_bridge()
        configs = bridge.get_server_configs()
        sessions = bridge.active_sessions
        
        servers = []
        total_tools = 0
        active_count = 0
        
        for name, config in configs.items():
            status = "offline"
            tool_count = 0
            
            if name in sessions:
                status = "connected"
                active_count += 1
                try:
                    # Get session and count tools
                    session_data = sessions[name]
                    if "session" in session_data:
                        tools_res = await session_data["session"].list_tools()
                        tool_count = len(tools_res.tools)
                        total_tools += tool_count
                except Exception as e:
                    logger.warning(f"[MCP_API] Could not fetch tool count for {name}: {e}")

            servers.append({
                "name": name,
                "command": config.get("command"),
                "args": config.get("args", []),
                "env": config.get("env", {}),
                "status": status,
                "tool_count": tool_count
            })
            
        return {
            "servers": servers,
            "active_count": active_count,
            "total_tools": total_tools
        }
    except Exception as e:
        logger.error(f"[MCP_API] Failed to list servers: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/add")
async def add_mcp_server(
    name: str = Body(...),
    command: str = Body(...),
    args: list = Body(None),
    env: dict = Body(None)
):
    """Add or update an MCP server configuration."""
    try:
        bridge = get_mcp_bridge()
        config = {
            "command": command,
            "args": args or [],
            "env": env or {}
        }
        
        success = await bridge.add_server(name, config)
        if success:
            return {"status": "success", "message": f"MCP server '{name}' added successfully"}
        else:
            raise HTTPException(status_code=500, detail=f"Failed to persist MCP server '{name}'")
    except Exception as e:
        logger.error(f"[MCP_API] Failed to add server: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/remove/{name}")
async def remove_mcp_server(name: str):
    """Remove and shutdown an MCP server."""
    try:
        bridge = get_mcp_bridge()
        # Bridge.remove_server needs to be implemented or handled via config removal
        # For now, we'll try to stop the session if it exists and remove from config
        
        if name in bridge.active_sessions:
            await bridge.close_session(name)
            
        # We need a method to remove from bridge.config and save to mcp_servers.json
        # Implementing a simple version here or extending bridge
        if hasattr(bridge, "remove_server"):
             success = await bridge.remove_server(name)
        else:
            # Fallback direct config manipulation if remove_server is missing
            if name in bridge.config:
                del bridge.config[name]
                bridge._save_config() # If this exists
                success = True
            else:
                success = False
                
        if success:
            return {"status": "success", "message": f"MCP server '{name}' removed"}
        else:
            raise HTTPException(status_code=404, detail=f"MCP server '{name}' not found")
    except Exception as e:
        logger.error(f"[MCP_API] Failed to remove server: {e}")
        raise HTTPException(status_code=500, detail=str(e))
