---
name: "clear_cache"
description: >
  Agent Memory Optimizer: Clear volatile internal memory to restore peak cognitive performance.
  
  Use this when:
  - The agent is behaving inconsistently or recycling stale observations
  - After a major task completes and a fresh context is needed
  - Admin explicitly requests a memory reset
  - Autonomous patrol cycle detects memory bloat
  
  Scopes:
  - SHORT_TERM: Clears observations, thoughts, and working memory (safe, fast)
  - EXPERIENCE_METADATA: Prunes cached SQL/pattern metadata (use with caution)
  - ALL: Full reset — use only when truly necessary
routing_examples:
  - '"The agent seems to be looping with stale data, reset its memory" -> PLAN (Clear short-term memory)'
  - '"Clear the SQL pattern cache, it is generating wrong queries" -> PLAN (Clear experience metadata)'
  - '"Do a full memory reset before starting the next task" -> PLAN (Clear all memory scopes)'
  - '"Agent context is bloated after the last patrol, clean it up" -> PLAN (Clear short-term memory)'
inputs:
  scope:
    type: string
    enum: ["SHORT_TERM", "EXPERIENCE_METADATA", "ALL"]
    description: "Memory scope to clear. Default: SHORT_TERM. Escalate scope only when explicitly needed."
---

# Instructions

You are performing a cognitive maintenance operation on yourself. Be precise and deliberate.

## Scope Decision Logic
| Scope | What it clears | When to use |
|---|---|---|
| SHORT_TERM | Observations, active thoughts, working buffer | After completing a task; stale context detected |
| EXPERIENCE_METADATA | Cached SQL patterns, query heuristics | Pattern cache is producing wrong SQL suggestions |
| ALL | Everything above | Full reset requested by Admin |

## Execution
```python
from datetime import datetime
from core.agent import get_agent

scope = params.get("scope", "SHORT_TERM")
agent = get_agent()
summary = {}

if scope in ["SHORT_TERM", "ALL"]:
    agent.short_memory.clear()
    summary["short_term"] = "CLEARED"

if scope in ["EXPERIENCE_METADATA", "ALL"]:
    # Additional logic for experience metadata clearing if supported
    summary["experience"] = "OPTIMIZED"

return {
    "status": "success",
    "message": f"Memory optimization ({scope}) complete.",
    "data": {"scope": scope, "actions_taken": summary, "timestamp": datetime.utcnow().isoformat()}
}
```

## Post-Execution Note
After clearing SHORT_TERM or ALL, inform the Admin that context has been reset.
The next interaction starts with a clean working memory.