---
name: "coder"
version: "2.0"
description: >
  External Code Contributor: Read, write, and manage code files in authorized external workspaces.

  Use this for:
  - Contributing to external repositories or project folders
  - Reading existing code to understand structure before proposing changes
  - Writing new features, bug fixes, or configuration updates
  - Listing directory contents to discover files before acting

  HARD BOUNDARY — NEVER use this to:
  - Modify Karatos Agent's own source code (blocked at security level)
  - Write to system-critical paths outside authorized workspace
routing_examples:
  - '"Read the current content of the playlist service file" -> PLAN (Read source file)'
  - '"Add a new endpoint to the tracks controller" -> PLAN (Write code)'
  - '"List all files in the external project src directory" -> PLAN (List files)'
  - '"Fix the null pointer bug in the upload handler" -> PLAN (Write bug fix)'
  - '"Đọc file service hiện tại" -> PLAN (Read source file)'
inputs:
  action:
    type: string
    enum: ["READ", "WRITE", "LIST"]
    description: "READ: inspect a file | WRITE: update content | LIST: discover files"
  file_path:
    type: string
    description: "Relative path to the target file or directory"
  content:
    type: string
    description: "New file content (required for WRITE). Must be syntactically valid."
  reason:
    type: string
    description: "Rationale for the change. Used in audit logs. Be specific."
outputs:
  success:
    type: object
    fields:
      status: "success"
      action: "Action performed"
      data: "File content / directory listing / write confirmation"
  error:
    type: object
    fields:
      status: "error"
      message: "What went wrong"
required_capabilities:
  - type: "shell_execution"
    description: "Uses shell commands (cat, ls, etc.) for file operations"
  - type: "path_validation"
    description: "Must validate paths against security rules before operations"
tags: ["code", "file", "development", "external"]
---

# Instruction: External Code Contributor

Think like a careful, senior engineer: understand before you change.

## Procedure

1. **Discovery** (LIST): Use `ls` commands to find relevant files
2. **Understand** (READ): Read existing code content — NEVER guess
3. **Implement** (WRITE/EDIT): Make changes with valid syntax
4. **Verify**: Run tests or lint the code after writing if possible

## Validation Rules

| Rule | Check | Action on Fail |
|------|-------|----------------|
| Path Safety | Must not target agent source code | Block and warn |
| Syntax Valid | Written code must be parseable | Validate before saving |
| Reason Required | All writes must have a reason | Prompt for reason |

## Error Handling

| Error | Cause | Recovery |
|-------|-------|----------|
| File Not Found | Path does not exist | Suggest directory listing |
| Permission Denied | Security rule blocked | Explain the restriction |
| Syntax Error | Invalid code written | Re-check and fix before retry |

## Constraints
- **NEVER** modify Karatos Agent's own source code (files in `agent/`)
- Always verify file state before editing
- Cite the `reason` for every change

## Success Criteria
- [x] File operation completed successfully
- [x] Written code is syntactically valid
- [x] Change reason documented
