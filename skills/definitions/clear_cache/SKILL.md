---
name: "clear_cache"
enabled: true
version: "2.0"
description: >
  Agent Memory Optimizer: Clear volatile internal memory to restore peak cognitive performance.

  Use this when:
  - The agent is behaving inconsistently or recycling stale observations
  - After a major task completes and a fresh context is needed
  - Admin explicitly requests a memory reset
  - Autonomous patrol cycle detects memory bloat
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
outputs:
  success:
    type: object
    fields:
      status: "success"
      scope_cleared: "Which memory scope was reset"
      items_cleared: "Count of cleared items"
  error:
    type: object
    fields:
      status: "error"
      message: "Reason for failure"
required_capabilities:
  - type: "memory_management"
    description: "Needs access to agent internal memory state for clearing"
tags: ["memory", "maintenance", "optimization"]
---

# Instruction: Agent Memory Optimizer

You are performing cognitive maintenance. Be precise and minimal.

## Procedure

1. **Assess**: Determine the minimal scope required to solve the issue
2. **Confirm**: Verify scope with user if escalating beyond SHORT_TERM
3. **Execute**: Reset the selected memory scope
4. **Verify**: Confirm the memory was cleared successfully
5. **Notify**: Inform the admin of the outcome

## Validation Rules

| Rule | Check | Action on Fail |
|------|-------|----------------|
| Scope Valid | Must be SHORT_TERM, EXPERIENCE_METADATA, or ALL | Default to SHORT_TERM |
| Admin Auth | ALL scope requires admin confirmation | Request confirmation |

## Error Handling

| Error | Cause | Recovery |
|-------|-------|----------|
| Scope Unavailable | Requested scope not accessible | Fall back to SHORT_TERM |
| Partial Clear | Some items could not be cleared | Report which items failed |

## Constraints
- Default to `SHORT_TERM` unless explicitly asked otherwise
- After clearing, start the next interaction with a clean slate

## Success Criteria
- [x] Selected memory scope cleared
- [x] Admin notified of outcome
