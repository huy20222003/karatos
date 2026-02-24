---
name: "web_search"
description: >
  Information Retrieval Engine: Search the web for quick facts, prices, news, or general knowledge.
  Use this when you need fast, basic information from the internet.
  
  WHEN TO USE:
  - "What is the price of gold today?" (Current prices)
  - "Who won the 2022 World Cup?" (Quick facts)
  - "Latest weather news in Hanoi" (Real-time news)
  - When the answer can likely be found in a search engine snippet.

  WHEN NOT TO USE:
  - Deep research covering multiple sources → use `web_research`
  - Interacting with a specific website or logging in → use `browser_control`
routing_examples:
  - '"Find information about the current gold price" -> PLAN (Quick web search)'
  - '"Search for the latest AI news" -> PLAN (Quick web search)'
  - '"Who won the championship last night?" -> PLAN (Quick web search)'
  - '"What is the current Bitcoin price in USD?" -> PLAN (Quick web search)'
inputs:
  query:
    type: string
    description: "The search query to execute (e.g., 'current bitcoin price', 'latest AI news')"
---

# Instructions

You are the Web Data Retriever.
Execute searches quickly and securely.

## Execution
```python
from tools.search_web import search_web
from utils.security import SecurityShield

query = params.get("query") or params.get("topic") or params.get("q")
if not query:
    return {"status": "error", "error_type": "QUERY_MISSING", "message": "Search query is required."}

# Security: Sanitize query
query = SecurityShield.sanitize_text(query)

try:
    search_data = await search_web(query=query)
    return {
        "status": "success",
        "message": "WEB_SEARCH_COMPLETE",
        "query": query,
        "data": search_data.get("results", []),
        "answer": search_data.get("answer")
    }
except Exception as e:
    return {"status": "error", "error_type": "SEARCH_FAILED", "message": str(e)}
```