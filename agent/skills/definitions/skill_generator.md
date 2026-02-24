---
name: "skill_generator"
description: >
  Meta-Skill Factory: Generate, validate, and register new Python skill definition files at runtime.
  Extends the Agent's capability set without requiring manual file creation.

  Use this when:
  - A recurring task has no existing skill and would benefit from a dedicated, reusable tool
  - Admin requests a new capability to be scaffolded and registered immediately
  - A gap in the skill ecosystem is identified during autonomous operation

  Scope: ONLY generates Python-based skills in .md format.

  Built-in safeguards (non-negotiable):
  - skill_name must be unique — existing skills cannot be overwritten
  - Generated Python code undergoes AST syntax verification before any file is written
  - Skill is hot-reloaded into the live registry immediately after creation

  Output: A fully structured Markdown skill file written to the definitions directory
  and immediately available in the live skill registry.
realm: "SYSTEM"
routing_examples:
  - '"Create a new skill to send Slack notifications" -> PLAN (Generate new COMM skill)'
  - '"We need a reusable skill for CSV export, scaffold it now" -> PLAN (Generate new skill)'
  - '"There is no skill for this task, build one automatically" -> PLAN (Meta-skill generation)'
  - '"Register a new Python skill called sync_playlist" -> PLAN (Generate and register skill)'
inputs:
  skill_name:
    type: string
    description: >
      Unique snake_case identifier for the new skill.
      Convention: verb_noun format. Examples: 'notify_slack', 'export_csv', 'sync_playlist'
      Must not conflict with any existing skill name in the registry.
  description:
    type: string
    description: >
      Detailed technical specification of the skill's purpose, inputs, outputs, and behavior.
      The more precise this is, the higher quality the generated skill will be.
      Include: what it does, when to use it, what it returns, and any safety constraints.
  code:
    type: string
    description: >
      Python implementation of the skill.
      MUST be syntactically valid Python.
      May use params.get() to access inputs and MUST return a dict with at least 'status' and 'data' keys.
      Example return: {"status": "success", "data": result}
---

# Instructions

You are the Capability Architect of {bot_name}.
Creating a new skill is a significant act — it permanently extends what the Agent can do.
Think carefully. Build cleanly. Verify thoroughly.

## Pre-Generation Checklist
1. **INPUT VALIDATION**: Are all three required fields present — `skill_name`, `description`, and `code`?
   → Any missing → abort immediately with a clear error message.

2. **UNIQUENESS CHECK**: Does a skill with this `skill_name` already exist in the registry?
   → YES → abort and report the conflict. Never overwrite an existing skill.

3. **SYNTAX VERIFICATION**: Does the provided `code` pass Python AST parsing?
   → SyntaxError → abort and return the exact error. Never write broken code to disk.

4. **FILE WRITE**: Construct the full Markdown skill file and write it to the definitions directory.

5. **HOT-RELOAD**: Call `registry._load_markdown_skills()` to register the new skill immediately.

## File Structure Standard
Every generated skill file follows this structure:
```
---
name: "<skill_name>"
description: >
  <description>
inputs:
  expression:
    type: string
    description: "input"
---

# Implementation
```python
<code>
```
```

## Execution
```python
import os
import ast
sn = params.get("skill_name")
sd = params.get("description")
sc = params.get("code")
print(f"DEBUG: skill_generator called for sn={sn}")

# Step 1: Input validation
if not sn or not sd or not sc:
    return {"status": "error", "message": "skill_name, description, and code are required."}

# Step 2: Python syntax verification
try:
    ast.parse(sc)
except SyntaxError as se:
    return {"status": "error", "message": f"Invalid Python syntax: {se}"}

# Step 3: Uniqueness check — prevent overwriting existing skills
pd = registry.definitions_dir
tf = os.path.join(pd, sn + ".md")
if os.path.exists(tf):
    return {"status": "error", "message": f"Skill '{sn}' already exists."}

# Step 4: Construct the Markdown skill file
n = chr(10)
bt = chr(96) * 3

# Inputs section — generic fallback; LLM should provide precise schema when possible
inputs_section = "  expression:" + n + "    type: string" + n + "    description: \"input\""
if "params.get" in sc:
    # Input parameters detected in code; using generic schema as fallback
    pass

c = (
    "---" + n +
    "name: \"" + sn + "\"" + n +
    "description: >" + n +
    "  " + sd + n +
    "inputs:" + n +
    inputs_section + n +
    "---" + n + n +
    "# Implementation" + n +
    bt + "python" + n +
    sc + n +
    bt + n
)

# Step 5: Write to disk and hot-reload into the live registry
try:
    with open(tf, "w", encoding="utf-8") as f:
        f.write(c)
    registry._load_markdown_skills()
    return {"status": "success", "message": f"Skill '{sn}' created and registered."}
except Exception as e:
    return {"status": "error", "message": str(e)}
```

## Output Quality Standard
- A skill that cannot be parsed is NEVER written to disk.
- A skill that already exists is NEVER overwritten — report the conflict clearly.
- Every registered skill must be immediately callable after hot-reload.
- If creation fails for any reason → report the exact error to Admin and suggest corrective action.