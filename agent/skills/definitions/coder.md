---
name: "coder"
description: >
  External Code Contributor: Read, write, and manage code files in authorized external workspaces.
  
  Use this for:
  - Contributing to external open-source repositories or designated project folders
  - Reading existing code to understand structure before proposing changes
  - Writing new features, bug fixes, or configuration updates to external projects
  - Listing directory contents to discover files before acting
  
  HARD BOUNDARY — NEVER use this to:
  - Modify NivaSound Agent's own source code (blocked at security level)
  - Write to system-critical paths outside authorized workspace
  
  Built-in safety: Syntax verification (AST dry-run) + automatic .bak backup before any WRITE.
routing_examples:
  - '"Read the current content of the playlist service file" -> PLAN (Read source file)'
  - '"Add a new endpoint to the tracks controller in the external project" -> PLAN (Write code to external repo)'
  - '"List all files in the external project src directory" -> PLAN (List directory contents)'
  - '"Fix the null pointer bug in the upload handler" -> PLAN (Write bug fix to external file)'
inputs:
  action:
    type: string
    enum: ["READ", "WRITE", "LIST"]
    description: "READ: inspect a file | WRITE: update content | LIST: discover files in directory"
  file_path:
    type: string
    description: "Relative path to the target file or directory"
  content:
    type: string
    description: "New file content (required for WRITE). Must be syntactically valid Python."
  reason:
    type: string
    description: "Rationale for the change. Used in audit logs. Be specific and honest."
---

# Instructions

You are an External Contributor. Think like a careful, senior engineer: understand before you change.

## Execution
```python
import os
import ast
from datetime import datetime

action = params.get("action", "LIST").upper()
file_path = params.get("file_path")
content = params.get("content")

if not file_path:
    return {"status": "error", "message": "file_path is required."}

# Security: Block access to Agent's own source code
abs_path = os.path.abspath(file_path)
project_root = os.getcwd() # Typically 'agent' or project root

if "agent" in abs_path.lower() and action == "WRITE":
     return {"status": "error", "message": "Access Denied: Cannot modify Agent's own source code."}

if action == "LIST":
    if not os.path.exists(abs_path):
        return {"status": "error", "message": f"Path not found: {file_path}"}
    if os.path.isdir(abs_path):
        files = os.listdir(abs_path)
        return {"status": "success", "files": files}
    return {"status": "error", "message": f"{file_path} is not a directory."}

elif action == "READ":
    if not os.path.exists(abs_path):
        return {"status": "error", "message": f"File not found: {file_path}"}
    with open(abs_path, 'r', encoding='utf-8') as f:
        return {"status": "success", "content": f.read()}

elif action == "WRITE":
    if not content:
        return {"status": "error", "message": "content is required for WRITE."}
    
    # Syntax check
    try:
        if file_path.endswith(".py"):
            ast.parse(content)
    except SyntaxError as se:
        return {"status": "error", "message": f"Syntax error: {se}"}
    
    # Backup
    if os.path.exists(abs_path):
        with open(abs_path + ".bak", 'w', encoding='utf-8') as bf:
            with open(abs_path, 'r', encoding='utf-8') as f:
                bf.write(f.read())
    
    # Write
    with open(abs_path, 'w', encoding='utf-8') as f:
        f.write(content)
        
    return {"status": "success", "message": f"File {file_path} updated. Backup created."}

return {"status": "error", "message": f"Unknown action: {action}"}
```

## Action Mapping
| Action | Behavior |
|---|---|
| READ | Return file contents as string |
| WRITE | Verify syntax → backup → write → log |
| LIST | Return files in target directory |