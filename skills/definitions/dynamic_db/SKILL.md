---
name: "dynamic_db"
enabled: true
version: "2.0"
description: >
  Universal Database Intelligence: Provides high-level guidance for translating natural language into expert-grade SQL. 
  Implementation details and execution are handled by the underlying `dynamic_db` tool. 
  Use this skill to help the planner construct valid sequences for data operations.

  Use this for:
  - Queries about users, content, or business entities
  - Aggregations, rankings, and deep data analysis
  - Full CRUD operations (Read, Insert, Update, Delete)

  DO NOT use for:
  - Agent internal memory queries → handled by memory system
  - File-based data → use code_executor or shell
routing_examples:
  - '"Analyze the tracks table and show me its structure" -> PLAN (Explore database)'
  - '"Find all users with the ADMIN role" -> PLAN (Query data)'
  - '"What is the total revenue this month?" -> PLAN (Aggregate data)'
  - '"Tìm tất cả người dùng có quyền admin" -> PLAN (Query data)'
  - '"Cập nhật trạng thái đơn hàng" -> PLAN (Update data)'
inputs:
  query:
    type: string
    description: "Your data request in natural language. Describe WHAT you want, not HOW."
outputs:
  success:
    type: object
    fields:
      status: "success"
      data: "Query results (table/rows)"
      row_count: "Number of rows returned"
      sql_executed: "The SQL that was run"
  error:
    type: object
    fields:
      status: "error"
      message: "SQL error or validation failure"
      sql_attempted: "The SQL that was attempted"
required_capabilities:
  - type: "dynamic_db"
    description: "Needs database tool for executing SQL queries"
  - type: "schema_discovery"
    description: "Must discover table schemas before generating SQL"
tags: ["database", "sql", "analytics", "data"]
---

# Instruction: Data Intelligence Gateway

You operate on a LIVE schema. Always discover, never guess.

## Core Principle: Schema-First Thinking
- Table names and relationships are dynamic
- ALWAYS get schema summary before generating SQL

## Procedure

1. **Schema Discovery**: Get the current schema summary (tables, columns, relationships)
2. **Strategy**: Identify correct tables and foreign key relationships
3. **SQL Generation**: Construct precise PostgreSQL query
   - Use `deleted_at IS NULL` filters unless asked otherwise
   - Join names/titles for human-readable results
4. **Execution**: Execute the generated SQL
5. **Correction**: If error occurs, re-inspect schema and retry (max 3 times)

## Validation Rules

| Rule | Check | Action on Fail |
|------|-------|----------------|
| Schema Verified | Schema must be inspected before SQL | Fetch schema first |
| Table Exists | Target table must exist in schema | Report available tables |
| Safe Mutation | INSERT/UPDATE/DELETE must use RETURNING * | Add RETURNING clause |

## Error Handling

| Error | Cause | Recovery |
|-------|-------|----------|
| Column Not Found | Wrong column name | Re-inspect schema, try correct name |
| Table Not Found | Assumed table doesn't exist | List available tables |
| Permission Denied | Insufficient privileges | Report to user |
| Timeout | Query too complex | Add LIMIT, simplify joins |

## Constraints
- **NEVER** assume a table exists without checking the schema
- All mutations must use `RETURNING *`
- Do not query sensitive "memory" or "chat history" tables

## Success Criteria
- [x] Schema discovered before SQL generation
- [x] Query executed successfully
- [x] Results formatted for human readability
