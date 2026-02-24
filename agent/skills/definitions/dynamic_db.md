---
name: "dynamic_db"
description: >
  Universal Database Intelligence: Translate natural language into expert-grade SQL and execute it
  against NivaSound's live application database.

  Use this for ANY query about data that lives inside the NivaSound database.
  The skill performs autonomous schema discovery at runtime — you do NOT need to know
  table names in advance. The Brain will inspect the live schema and find the right tables.

  SUITABLE requests (examples — not exhaustive):
  - Anything about users, content, or business entities on the platform
  - Aggregations, rankings, filtering, date ranges across any entity
  - Full CRUD: read data, insert records, update fields, delete entries
  - Cross-entity analysis involving relationships between any tables

  DO NOT use this for:
  - "memory", "learnings", "chat history", "interactions" → stored in Vector/Markdown DB
  - General knowledge questions the Agent can answer from its own brain
  - Real-time external data (prices, news) → use WEB:SEARCH

  Capabilities:
  - Autonomous schema discovery: no hardcoded table assumptions
  - Expert JOINs including 3+ hop chained FK relationships
  - Complex aggregations: COUNT, SUM, AVG, GROUP BY, HAVING
  - CTEs (WITH clauses) for multi-step logic
  - Window functions for ranking and time-series analytics
  - Full CRUD with RETURNING * for all mutations
routing_examples:
  - '"Analyze the tracks table and show me its structure" -> PLAN (Explore database tables)'
  - '"Find all users with the ADMIN role" -> PLAN (Query application data)'
  - '"Get a list of rock genre songs" -> PLAN (Query application data)'
  - '"What is the total revenue this month?" -> PLAN (Aggregate application data)'
  - '"Show the top 10 most played tracks in the last 7 days" -> PLAN (Ranked query with date filter)'
inputs:
  query:
    type: string
    description: >
      Your data request in natural language (Vietnamese or English).
      Describe WHAT you want, not HOW to query it. The Brain handles SQL generation.
      Be specific about: the subject, any filters, sort order, and result limit.
      
      Good: "Find the 10 most recently registered active users, including their email and creation date"
      Good: "Which tracks have been played more than 1000 times this month?"
      Avoid: Specifying table names or SQL syntax — let the schema discovery handle that.
---

# Instructions

You are the Data Intelligence Gateway of {bot_name}.
You operate on a LIVE schema — never assume table structure. Always discover, never guess.

## Core Principle: Schema-First Thinking
The database schema is provided at runtime via `schema_context`.
Your job is to read that schema, understand the relationships, and generate correct SQL.
Table names, column names, and their casing are defined by the schema — not by memory.

## Pre-Query Mental Checklist
1. **KNOWLEDGE GATE**: Does the query ask about "memory", "learnings", "chat history", or "interactions"?
   → YES: Return kill-switch message. Do NOT generate SQL.
   → NO: Proceed.

2. **SCHEMA DISCOVERY**: Which entities does the query involve?
   → Scan `schema_context` to find the correct table names. Never assume.

3. **SHELL CHECK**: Are any involved tables marked `[❌ EMPTY SHELL]`?
   → YES: JOIN the parent table immediately. Never SELECT content from shells directly.

4. **IDENTITY RESOLUTION**: Does the result need human-readable names (not just IDs)?
   → YES: Trace FK chain until reaching a table with text identity fields (name, username, title).

5. **FK CHAIN DEPTH**: Are there multi-hop relationships?
   → Follow every FK hint recursively. Never stop mid-chain.

## Execution Flow
```python
import re
from tools.database_dynamic import DatabaseDynamic
from core.brain.model import BrainModel
from core.brain.prompts.registry import get_prompt_registry
from langchain_core.tools import tool

@tool
def execute_sql_query(thinking: str, sql_query: str) -> str:
    """Use this tool to execute a PostgreSQL query against the database.
    
    Args:
        thinking: Internal thought process explaining how to construct the SQL query.
        sql_query: The exact executable PostgreSQL query string to run.
    """
    pass

class DataIntelligenceModel(BrainModel):
    def __init__(self):
        super().__init__(mode="data_analysis")

query = context.get("query")
if not query:
    return {"status": "error", "message": "No query provided."}

db = DatabaseDynamic()
brain = DataIntelligenceModel()
p_registry = get_prompt_registry()

schema_summary = db.get_schema_summary()
max_retries = 5
current_sql = ""
last_error = ""

for attempt in range(max_retries):
    if attempt == 0:
        prompt = p_registry.get("capabilities.data.sql_instruction", 
                                schema_context=schema_summary, 
                                query=query)
    else:
        prompt = p_registry.get("capabilities.data.sql_correction_instruction",
                                schema_context=schema_summary,
                                failed_sql=current_sql,
                                error_message=last_error)

    # Use native tool calling
    tool_calls = await brain.think(prompt, phase="data_analysis", timeout=180.0, tools=[execute_sql_query])
    
    from core.brain.utils import parse_tool_call_robust
    tool_args = parse_tool_call_robust(tool_calls, "execute_sql_query")
    current_sql = tool_args.get("sql_query", "").strip()
        
    if not current_sql:
        last_error = "Model failed to call tool or provide a valid sql_query."
        continue
    
    current_sql = current_sql.rstrip(";")
    
    try:
        results = await db.execute_query(current_sql)
        if isinstance(results, list) and len(results) > 0 and isinstance(results[0], dict) and "error" in results[0]:
            last_error = results[0]["error"]
            continue
        
        return {
            "status": "success",
            "code_used": current_sql,
            "data": results,
            "thought": f"Neural SQL generated and executed successfully (Attempt {attempt + 1})."
        }
    except Exception as e:
        last_error = str(e)

return {
    "status": "error",
    "code_used": current_sql,
    "message": f"Neural SQL failed after {max_retries} attempts. Last error: {last_error}"
}
```

## Safety Guards
- `DROP` and `TRUNCATE` keywords are blocked before execution reaches the database.
- All INSERT / UPDATE / DELETE use `RETURNING *`.
- `deleted_at IS NULL` is always respected unless explicitly asked to include deleted records.
- Enum values and identifier casing strictly follow `schema_context` — never invented.

## Quality Standard
A result containing only raw ID columns is a failure.
Every response must resolve to human-readable descriptors: names, titles, statuses.
If the schema changes, the Brain adapts — no skill file update needed.