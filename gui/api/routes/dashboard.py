"""
Dashboard API Routes — Agent overview, memory stats, decisions, tools.
"""
from fastapi import APIRouter
from datetime import datetime
from config.settings import settings

router = APIRouter()


@router.get("/overview")
async def get_overview():
    """Agent overview: identity, status, mood, energy, uptime."""
    from gui.server import get_agent

    agent = get_agent()
    status = agent.get_status() if agent else {}

    # Get skill and tool counts
    skill_count = 0
    tool_count = 0
    try:
        # Use singleton registries for accurate counts
        from skills.registry import get_skill_registry
        from tools.registry import get_tool_registry
        
        skill_registry = get_skill_registry()
        tool_registry = get_tool_registry()
        
        skill_count = len(skill_registry.skills)
        # tool_registry.get_tool_schemas() combines local + MCP tools
        tool_schemas = await tool_registry.get_tool_schemas()
        tool_count = len(tool_schemas)
    except Exception as e:
        from utils.logger import get_logger
        logger = get_logger()
        logger.warning(f"[DASHBOARD] Stats retrieval failed: {e}")

    # Mood and energy tracked on agent after each brain cycle
    mood = getattr(agent, "_last_mood", "OPTIMISTIC") if agent else "OFFLINE"
    energy = getattr(agent, "_last_energy", 1.0) if agent else 0.0

    return {
        "agent": {
            "name": settings.bot_name,
            "username": settings.bot_username,
            "mood": mood,
            "energy": energy,
            "llm_provider": settings.llm_provider,
            "model": _get_active_model(settings),
            "language": settings.user_language,
            "avatar_url": settings.avatar_model_url,
        },
        "status": status,
        "skill_count": skill_count,
        "tool_count": tool_count,
        "last_patrol": getattr(agent, "_last_patrol", None).isoformat() + "Z" if agent and getattr(agent, "_last_patrol", None) else None,
        "timestamp": datetime.utcnow().isoformat() + "Z",
    }


@router.get("/memory")
async def get_memory_stats():
    """Memory categories with counts."""
    from gui.server import get_agent

    agent = get_agent()
    memory = getattr(agent, "memory", None)

    if not memory:
        return {"categories": {}, "total": 0}

    try:
        engine = getattr(memory, "engine", None)
        if engine:
            count = engine.get_count()
            # Get per-category counts by scanning directories
            from memory.persistent import MemoryCategory
            categories = {}
            for cat in MemoryCategory:
                try:
                    entries = engine.list_by_category(cat.value, limit=1000)
                    categories[cat.value] = len(entries)
                except:
                    categories[cat.value] = 0
            return {"categories": categories, "total": count}
    except Exception as e:
        return {"categories": {}, "total": 0, "error": str(e)}


@router.get("/decisions")
async def get_decisions():
    """Recent decision history from brain state."""
    from gui.server import get_agent

    agent = get_agent()
    brain = getattr(agent, "brain", None)

    decisions = []
    if brain and hasattr(brain, "decision_history"):
        decisions = brain.decision_history[-20:]

    # Format timestamps to DD/MM/YYYY HH:MM:SS
    formatted = []
    for d in decisions:
        ts = d.get("timestamp", "")
        if ts and "-" in ts[:10]:
            try:
                parts = ts.split(" ")
                d_parts = parts[0].split("-")
                if len(d_parts) == 3:
                    ts = f"{d_parts[2]}/{d_parts[1]}/{d_parts[0]}"
                    if len(parts) > 1:
                        ts += f" {parts[1]}"
            except Exception:
                pass
        formatted.append({
            "timestamp": ts,
            "decision": d.get("decision", ""),
            "reasoning": d.get("reasoning", "")
        })

    return {"decisions": formatted}


@router.get("/tools")
async def get_tools():
    """Registered tools and MCP servers."""
    try:
        from tools.registry import get_tool_registry
        registry = get_tool_registry()

        # Build structured tool list
        tool_list = []
        for name, tool_data in registry.tools.items():
            meta = tool_data.get("meta", {})
            tool_list.append({
                "name": meta.get("name", name),
                "description": meta.get("description", ""),
                "version": meta.get("version", ""),
            })

        # MCP servers — check for active session inside the dict
        mcp_servers = []
        try:
            bridge = registry.get_mcp_bridge()
            if bridge:
                for sname in bridge.servers:
                    session_data = bridge.active_sessions.get(sname, {})
                    has_session = session_data.get("session") is not None if isinstance(session_data, dict) else False
                    mcp_servers.append({
                        "name": sname,
                        "connected": has_session
                    })
        except:
            pass

        return {"tools": tool_list, "mcp_servers": mcp_servers}
    except Exception as e:
        return {"tools": [], "mcp_servers": [], "error": str(e)}


@router.post("/patrol")
async def trigger_patrol():
    """Trigger a manual patrol cycle."""
    from gui.server import get_agent
    agent = get_agent()
    if not agent:
        return {"status": "error", "message": "Agent not running"}
    
    # Run in background to not block UI
    import asyncio
    asyncio.create_task(agent.patrol())
    
    return {"status": "success", "message": "Patrol started"}


@router.get("/patrol/status")
async def get_patrol_status():
    """Get the latest patrol status and thoughts."""
    from gui.server import get_agent
    agent = get_agent()
    if not agent:
        return {"status": "error", "message": "Agent not running"}
    
    status = {
        "last_patrol": agent._last_patrol.isoformat() + "Z" if agent._last_patrol else None,
        "cycle_count": agent._cycle_count,
        "interval_minutes": settings.scan_interval_minutes,
        "thoughts": agent.brain.decision_history[-5:] if hasattr(agent.brain, "decision_history") else []
    }
    return status


def _get_active_model(settings) -> str:
    provider = settings.llm_provider.lower().replace("-", "_")
    if provider == "ollama":
        return settings.ollama_model_name
    elif provider == "openai":
        return settings.openai_model_name
    elif provider == "anthropic":
        return settings.anthropic_model_name
    elif provider == "deepseek":
        return settings.deepseek_model_name
    elif provider == "claude_web":
        return settings.claude_web_model_name
    return settings.llm_provider
