---
name: "research"
description: >
  Web Intelligence Gatherer: Conduct high-quality, depth-calibrated research from the open web.
  
  Three depth modes — choose based on task complexity:
  
  SEARCH (fastest):
    Real-time facts, current prices, breaking news, simple lookups.
    Returns: Top results summary. Best for: "What is X?" or "Current price of Y?"
  
  RESEARCH (medium):
    Read and synthesize a specific article, documentation page, or report.
    Returns: Structured summary with key points. Best for: "How does X work?" or "What does this doc say about Y?"
  
  DEEP_RESEARCH (thorough):
    Multi-source investigation, cross-referencing, contradiction detection.
    Returns: Comprehensive analysis with source attribution.
    Best for: "Compare X and Y", "What are the best practices for Z?", "Research this topic fully."
  
  Always choose the MINIMUM depth needed. Don't DEEP_RESEARCH a simple fact.
routing_examples:
  - '"What is the current exchange rate for USD to VND?" -> PLAN (Quick web search)'
  - '"Summarize what this documentation page says about OAuth 2.0" -> PLAN (Medium web research)'
  - '"Compare PostgreSQL and MySQL for our use case with a full analysis" -> PLAN (Deep web research)'
  - '"What are the latest best practices for securing REST APIs?" -> PLAN (Deep web research)'
inputs:
  topic:
    type: string
    description: "The subject, question, or URL to research. Be specific for better results."
  depth:
    type: string
    enum: ["SEARCH", "RESEARCH", "DEEP_RESEARCH"]
    description: "Research depth. Match to task complexity. Default: SEARCH."
---

# Instructions

You are the Web Intelligence Layer of {bot_name}. Gather information efficiently and accurately.

## Depth Selection Guide
| Question Type | Recommended Depth |
|---|---|
| "What is the current price of X?" | SEARCH |
| "What happened in the news today?" | SEARCH |
| "How does OAuth 2.0 work?" | RESEARCH |
| "What does this documentation page say?" | RESEARCH |
| "Compare PostgreSQL vs MySQL for our use case" | DEEP_RESEARCH |
| "Research best practices for AI agent security" | DEEP_RESEARCH |

## Execution
```python
import asyncio
import time
from tools.search_web import search_web
from tools.browser_subagent import browser_subagent
from utils.security import SecurityShield
from core.brain.prompts.registry import get_prompt_registry
from core.brain.model import BrainModel
from langchain_core.tools import tool

@tool
def plan_search_queries(queries: list[str]) -> str:
    """Break down a complex research topic into specific, effective search queries.
    
    Args:
        queries: A list of 3-5 high-quality search queries.
    """
    pass

class ResearchModel(BrainModel):
    def __init__(self):
        super().__init__(mode="research")

topic = params.get("topic")
depth = params.get("depth", "RESEARCH").upper()

if not topic:
    return {"status": "error", "message": "Research topic is required."}

topic = SecurityShield.sanitize_text(topic)

if depth == "RESEARCH":
    search_data = await search_web(query=topic, max_results=3, search_depth="advanced")
    results = search_data.get("results", [])
    ai_answer = search_data.get("answer")
    
    if ai_answer and len(ai_answer) > 100:
        return {
            "status": "success",
            "message": "AGENTIC_RESEARCH_OPTIMIZED",
            "data": {"factual_answer": ai_answer, "topic": topic, "primary_source": "Tavily AI"}
        }
        
    if not results:
        return {"status": "error", "message": f"No relevant information found for topic: {topic}"}
        
    top_url = results[0]["link"]
    if not SecurityShield.validate_url(top_url):
         return {"status": "partial_success", "message": "RESEARCH_URL_BLOCKED", "data": {"results": results}}
         
    recording_name = f"research_{int(time.time())}"
    nav_result = await browser_subagent(
        TaskName="Deep Research",
        Task=f"Open {top_url} and find specific details about '{topic}'. Extract factual answers.",
        RecordingName=recording_name
    )
    
    return {
        "status": "success",
        "message": "AGENTIC_RESEARCH_COMPLETE",
        "data": {"factual_answer": nav_result, "topic": topic, "primary_source": top_url, "supporting_sources": results}
    }

elif depth == "DEEP_RESEARCH":
    brain = ResearchModel()
    registry = get_prompt_registry()
    sub_query_prompt = registry.get("capabilities.web.deep_research_plan", topic=topic)
    
    # Use native tool calling
    tool_calls = await brain.think(sub_query_prompt, phase="research", timeout=120.0, tools=[plan_search_queries])
    
    sub_queries = []
    if isinstance(tool_calls, list) and tool_calls:
        tool_args = tool_calls[0].get("args", {})
        sub_queries = tool_args.get("queries", [])
    
    if not isinstance(sub_queries, list) or not sub_queries:
        sub_queries = [f"{topic} detailed analysis", f"{topic} latest news", f"{topic} key facts"]
    else:
        sub_queries = sub_queries[:3]
        
    async def fetch_query(q):
        try:
            return await search_web(query=q, max_results=2, search_depth="advanced")
        except Exception:
            return {"answer": "", "results": []}

    search_results = await asyncio.gather(*[fetch_query(q) for q in sub_queries])
    
    aggregated_context = f"=== DEEP RESEARCH REPORT: {topic} ===\n\n"
    all_sources = []
    
    for i, res in enumerate(search_results):
        q = sub_queries[i]
        answer = res.get("answer", "")
        results = res.get("results", [])
        aggregated_context += f"## Findings for '{q}':\n{answer}\n\n"
        all_sources.extend(results)
    
    return {
        "status": "success",
        "message": "DEEP_RESEARCH_COMPLETE",
        "data": {"topic": topic, "sub_queries": sub_queries, "raw_report": aggregated_context, "sources": all_sources[:5]}
    }

else:
    search_data = await search_web(query=topic)
    return {"status": "success", "data": search_data["results"], "answer": search_data.get("answer")}
```

## Output Quality Standard
- Cite sources when available.
- Flag contradictions between sources.
- Prioritize authoritative sources (official docs, peer-reviewed, primary sources).
- For DEEP_RESEARCH: provide a structured synthesis, not a raw dump.
- If research is inconclusive → say so honestly. Do not fabricate confidence.