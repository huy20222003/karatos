"""
Memory API Routes — Detailed memory data for visualization.
"""
from fastapi import APIRouter, Query
from typing import Optional

router = APIRouter()


@router.get("/categories")
async def get_memory_categories():
    from gui.server import get_agent
    agent = get_agent()
    memory = getattr(agent, "memory", None)
    if not memory:
        return {"categories": [], "total": 0}

    try:
        engine = getattr(memory, "engine", None)
        if not engine:
            return {"categories": [], "total": 0}

        from memory.persistent import MemoryCategory
        categories = []
        total = 0
        for cat in MemoryCategory:
            try:
                entries = engine.list_by_category(cat.value, limit=1000)
                count = len(entries)
                total += count
                # Get 3 sample titles for preview
                samples = [getattr(e, "title", getattr(e, "key", "untitled"))[:60] for e in entries[:3]]
                categories.append({
                    "name": cat.value,
                    "count": count,
                    "samples": samples,
                })
            except Exception:
                categories.append({"name": cat.value, "count": 0, "samples": []})

        return {"categories": categories, "total": total}
    except Exception as e:
        return {"categories": [], "total": 0, "error": str(e)}


@router.get("/entries")
async def get_memory_entries(
    category: str = Query(..., description="Memory category name"),
    limit: int = Query(50, ge=1, le=200),
):
    """List entries in a specific memory category."""
    from gui.server import get_agent

    agent = get_agent()
    memory = getattr(agent, "memory", None)
    if not memory:
        return {"entries": [], "category": category}

    try:
        engine = getattr(memory, "engine", None)
        if not engine:
            return {"entries": [], "category": category}

        raw_entries = engine.list_by_category(category, limit=limit)
        entries = []
        for e in raw_entries:
            entries.append({
                "key": e.key,
                "title": getattr(e, "title", e.key),
                "category": category,
                "preview": str(e.content)[:200],
                "timestamp": e.created_at,
            })
        return {"entries": entries, "category": category}
    except Exception as e:
        return {"entries": [], "category": category, "error": str(e)}


@router.get("/graph")
async def get_memory_graph():
    """Graph data for 3D visualization: nodes = categories, size = count."""
    from gui.server import get_agent

    agent = get_agent()
    memory = getattr(agent, "memory", None)
    if not memory:
        return {"nodes": [], "links": []}

    try:
        engine = getattr(memory, "engine", None)
        if not engine:
            return {"nodes": [], "links": []}

        from memory.persistent import MemoryCategory
        nodes = []
        for i, cat in enumerate(MemoryCategory):
            try:
                entries = engine.list_by_category(cat.value, limit=1000)
                count = len(entries)
                if count > 0:
                    nodes.append({
                        "id": cat.value,
                        "count": count,
                        "index": i,
                    })
            except Exception:
                pass

        # Links: connect categories that share keywords (simple heuristic)
        links = []
        for i, n1 in enumerate(nodes):
            for j, n2 in enumerate(nodes):
                if i < j:
                    # Simple proximity: categories near in index are loosely connected
                    links.append({
                        "source": n1["id"],
                        "target": n2["id"],
                        "strength": 0.1,
                    })

        return {"nodes": nodes, "links": links}
    except Exception as e:
        return {"nodes": [], "links": [], "error": str(e)}
