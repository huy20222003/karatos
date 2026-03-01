---
# ============================================================
# SKILL DEFINITION — Professional Agentic AI Template v2.0
# ============================================================
# INSTRUCTIONS FOR CREATORS:
#   1. Copy this entire _template folder and rename it to your skill's snake_case name
#   2. Replace ALL placeholder values (wrapped in {curly_braces}) with actual content
#   3. Remove these instruction comments before committing
#   4. Ensure routing_examples are diverse (min 3, ideally 5+)
#   5. Do NOT hardcode specific tool names — describe CAPABILITIES instead
# ============================================================

name: "{skill_name}"
enabled: true
version: "1.0.0"
author: "{author_name}"

description: >
  {One-line capability summary: What this skill does and WHEN to use it.}
  
  USE WHEN:
  - {Scenario 1 — when this skill is the right choice}
  - {Scenario 2}
  
  DO NOT USE WHEN:
  - {Scenario where another capability is better suited}

# --- ROUTING INTELLIGENCE ---
# These examples train the Router to recognize requests that match this skill.
# Format: "User intent" -> PLAN (Brief reason)
# Be diverse: cover different phrasings, languages, edge cases.
routing_examples:
  - '"{Example user request in primary language}" -> PLAN ({Brief routing reason})'
  - '"{Example user request in secondary language}" -> PLAN ({Brief routing reason})'
  - '"{Edge case or alternative phrasing}" -> PLAN ({Brief routing reason})'

# --- INPUT SCHEMA ---
# Define what this skill expects to receive from the Planner.
# Each input must have: type, description. Optional: required, default, validation.
inputs:
  primary_input:
    type: string
    required: true
    description: >
      {What this input represents and how it should be formatted.}
    validation:
      min_length: 1
      max_length: 10000
    examples:
      - "{Example value 1}"
      - "{Example value 2}"
  
  optional_param:
    type: string
    required: false
    default: "{default_value}"
    description: >
      {Description of optional parameter and when to provide it.}

# --- OUTPUT SCHEMA ---
# Define what this skill produces so downstream nodes can parse results correctly.
outputs:
  success:
    type: object
    description: "Returned when the skill executes successfully."
    schema:
      status:
        type: string
        value: "success"
      data:
        type: any
        description: "{What the main result data contains}"
      message:
        type: string
        description: "Human-readable summary of what was accomplished."
  
  error:
    type: object
    description: "Returned when the skill encounters an error."
    schema:
      status:
        type: string
        value: "error"
      error_code:
        type: string
        description: "Machine-readable error identifier (e.g., INVALID_INPUT, TIMEOUT, PERMISSION_DENIED)."
      message:
        type: string
        description: "Human-readable explanation of what went wrong."
      recovery_hint:
        type: string
        description: "Suggested action to resolve the error."

# --- CAPABILITY REQUIREMENTS ---
# Declare what KIND of capabilities this skill needs (NOT specific tool names).
# The Brain will map these to available tools at runtime.
required_capabilities:
  - "{capability_type}: {description of what is needed}"
  # Examples:
  # - "shell_execution: Ability to run system commands on the host OS"
  # - "web_request: Ability to make HTTP requests to external APIs"
  # - "file_io: Ability to read and write files on the filesystem"
  # - "database_query: Ability to execute queries against a database"
  # - "browser_automation: Ability to control a web browser"

# --- TAGS ---
# Used for capability discovery and grouping.
tags:
  - "{category}"     # e.g., "system", "data", "communication", "research"
  - "{subcategory}"  # e.g., "file-ops", "web-scraping", "database"
---

# Skill: {Skill Display Name}

{Brief role definition: "You are the [Role Name] responsible for [core mission]."}

## Context Awareness

Before executing, consider:
- **OS Environment**: Check `os_platform` param to adapt commands for Windows/Linux/Mac.
- **User Intent**: Re-read the user's original request to ensure alignment.
- **Previous Results**: If this skill is part of a multi-step plan, review `task_outputs` from earlier steps.

## Procedure

### Step 1: {Validate & Prepare}
- Verify all required inputs are present and valid.
- If any input fails validation, return an error output immediately with `recovery_hint`.
- {Additional preparation logic}

### Step 2: {Core Execution}
- {Detailed instruction for the main action}
- {Explain the REASONING behind this step, not just the action}
- {If multiple approaches exist, describe the decision criteria}

### Step 3: {Verify & Report}
- Confirm the action was successful by {verification method}.
- If the action failed:
  - Analyze the error output.
  - Attempt ONE recovery strategy: {describe recovery}.
  - If recovery fails, return error output with full context.

## Validation Rules

| Rule | Check | On Failure |
|------|-------|------------|
| Input present | `{primary_input}` is not empty | Return error: `INVALID_INPUT` |
| {Custom rule} | {What to check} | {Error action} |

## Error Handling

| Error Code | Cause | Recovery |
|------------|-------|----------|
| `INVALID_INPUT` | Required input missing or malformed | Ask user to provide correct input |
| `EXECUTION_FAILED` | Core action returned an error | Log error, attempt retry once |
| `TIMEOUT` | Action took too long | Inform user, suggest simpler scope |
| `PERMISSION_DENIED` | Security policy blocked the action | Route to approval flow |

## Constraints

- **Security**: {Any security boundaries this skill must respect}
- **Performance**: {Expected execution time, resource limits}
- **Scope**: {What this skill explicitly does NOT do}

## Success Criteria

- [ ] All required inputs validated before execution
- [ ] Core action completed without unhandled errors
- [ ] Output matches the defined output schema
- [ ] User receives a clear, actionable response
