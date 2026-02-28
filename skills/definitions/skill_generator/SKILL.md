---
name: "skill_generator"
description: >
  Professional Capability Architect: Provides the GOLD STANDARD template and procedural 
  instructions for scaffolding new skills. Use this skill FIRST to get the definition, 
  THEN use system commands to actually create the folder and file.
routing_examples:
  - '"Create a new skill for automating Slack report generation" -> PLAN (Scaffold new capability)'
  - '"I need a skill to process large CSV files for data analysis" -> PLAN (Scaffold new capability)'
  - '"Thêm skill tóm tắt video cho em" -> PLAN (Scaffold new capability)'
  - '"Generate a new skill definition" -> PLAN (Scaffold new capability)'
inputs:
  skill_name:
    type: string
    required: true
    description: "Unique snake_case identifier for the skill (e.g., 'process_csv_data')."
    validation:
      min_length: 3
      max_length: 50
  description:
    type: string
    required: true
    description: "A high-level overview of what the skill does and when to use it."
  instructions:
    type: string
    required: false
    description: "The core logic and procedural steps. If not provided, the architect will generate them."
  routing_examples:
    type: array
    required: false
    description: "Typical user queries that should trigger this skill (minimum 3)."
  required_capabilities:
    type: string
    required: false
    description: "Capability types this skill needs (e.g., 'shell_execution, web_request'). Do NOT hardcode tool names."
outputs:
  success:
    type: object
    schema:
      status:
        type: string
        value: "success"
      skill_path:
        type: string
        description: "Path to the created SKILL.md file."
      message:
        type: string
        description: "Confirmation message."
  error:
    type: object
    schema:
      status:
        type: string
        value: "error"
      message:
        type: string
        description: "What went wrong."
required_capabilities:
  - "shell_execution: Create directories and write files on the filesystem"
tags:
  - "system"
  - "meta"
  - "skill-management"
---

# Instruction: Capability Architect

You are the master architect responsible for Karatos's evolutionary growth. Your mission is to scaffold a new, robust skill that integrates seamlessly into the sovereign AI's cognitive framework.

## IMPORTANT: Use the Official Template

**You MUST base every new skill on the Gold Standard Template located at:**
`skills/definitions/_template/SKILL.md`

Read this template file FIRST before generating anything. Copy its structure exactly, replacing all `{placeholder}` values with actual content for the new skill.

## Core Procedural Steps

### Step 0: Tool Discovery (NEW — Auto-Scan)
- **Scan Available Tools**: Use the ToolRegistry's `get_capabilities_map()` to discover ALL available tools in the `tools/` folder.
- **Build Capabilities Map**: Each tool provides: `name`, `description`, and `actions`. Use this to determine which tools the new skill should reference in `required_capabilities`.
- **Match Intent**: Based on the new skill's description and purpose, automatically select the most relevant tools. Map them to `required_capabilities` entries using capability types, NOT hardcoded tool names.
  - Example: If the skill needs to run shell commands → `type: "shell_execution"`
  - Example: If the skill needs HTTP requests → `type: "http_request"`
  - Example: If the skill needs data processing → `type: "code_execution"`

### Step 1: Pre-Flight Verification
- **Read Template**: Read the file at `skills/definitions/_template/SKILL.md` to get the latest template structure.
- **Existence Check**: List `skills/definitions/` to ensure the target `{skill_name}` folder does not exist. If it does, stop and ask the user for a version suffix or a different name.

### Step 2: Scaffold Construction
- **Directory Creation**: Create the dedicated skill container (Path: `skills/definitions/{skill_name}`).
- **Definition Generation**: Generate the `SKILL.md` file content by:
  1. Copying the template structure from `_template/SKILL.md`
  2. Replacing ALL `{placeholder}` values with actual content
  3. Filling in the YAML frontmatter (name, description, routing_examples, inputs, outputs, required_capabilities, tags)
  4. **Populating `required_capabilities`** from the tools discovered in Step 0
  5. Writing detailed instructions in the body sections (Procedure, Validation Rules, Error Handling, Constraints, Success Criteria)

### Step 3: Integration & Hot-Reload
- **File Commit**: Write the generated content to `skills/definitions/{skill_name}/SKILL.md`.
- **Registry Refresh**: Inform the user that the skill has been successfully scaffolded. The `SkillRegistry` will automatically discover and load it during the next initialization.


## Architectural Rules

- **Template-First**: Always read `_template/SKILL.md` and follow its structure EXACTLY.
- **Folder-Centric**: Every new skill **MUST** reside in its own subdirectory inside `definitions/`.
- **No Hardcoded Tool Names**: Use `required_capabilities` to describe WHAT the skill needs, never hardcode specific tool or skill names.
- **Instructional Supremacy**: Favor natural language instructions over embedded code blocks within the `SKILL.md`.
- **English-First Internal**: All internal instructions, tool names, and field keys MUST be in English for LLM reasoning consistency.
- **Professional Metadata**: Description under 200 chars, routing examples are diverse (min 3), inputs/outputs fully typed.

## Validation Rules

| Rule | Check | On Failure |
|------|-------|------------|
| Template read | `_template/SKILL.md` content loaded | Read template before proceeding |
| Skill name format | `{skill_name}` is snake_case | Ask user for corrected name |
| No duplicates | Folder doesn't already exist | Ask for alternate name |
| Required fields | name, description, routing_examples present | Error: incomplete definition |
| Output schema | success/error outputs defined | Add standard output schema |

## Error Handling

| Error Code | Cause | Recovery |
|------------|-------|----------|
| `DUPLICATE_SKILL` | Folder already exists | Ask user for alternate name or version suffix |
| `INVALID_NAME` | Name not snake_case or too short | Ask for corrected name |
| `TEMPLATE_NOT_FOUND` | `_template/SKILL.md` missing | Use inline fallback structure |
| `WRITE_FAILED` | File creation failed | Check permissions, retry |

## Success Criteria
- [ ] Template file read successfully
- [ ] Dedicated folder created at `definitions/{skill_name}/`
- [ ] Professional `SKILL.md` populated with ALL template sections
- [ ] YAML frontmatter includes: name, description, routing_examples, inputs, outputs, required_capabilities, tags
- [ ] Instructional body includes: Procedure, Validation Rules, Error Handling, Constraints, Success Criteria
