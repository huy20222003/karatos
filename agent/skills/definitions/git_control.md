---
name: "git_control"
description: >
  Git Version Control Manager: Perform professional Git operations for external repositories.
  
  Use this for:
  - Checking repository status before making changes (STATUS)
  - Creating isolated branches for specific fixes or features (BRANCH, CHECKOUT)
  - Staging and committing changes with descriptive messages (ADD, COMMIT)
  - Syncing with remote repositories (PUSH, PULL)
  - Inspecting recent commit history (LOG)
  
  Safety principles built-in:
  - Never commit to `main` directly without explicit Admin confirmation
  - Never stage `.env` files or files containing secrets
  - Always use conventional commit format: `feat:`, `fix:`, `chore:`, `docs:`
  
  Recommended workflow: STATUS → BRANCH → ADD → COMMIT → PUSH
routing_examples:
  - '"Check the current state of the repository before making changes" -> PLAN (Git status check)'
  - '"Create a new branch for the playlist sharing feature" -> PLAN (Git branch creation)'
  - '"Stage all changes and commit with a descriptive message" -> PLAN (Git add and commit)'
  - '"Push the latest commits to the remote origin" -> PLAN (Git push to remote)'
  - '"Show me the last 5 commits on this repository" -> PLAN (Git log inspection)'
inputs:
  action:
    type: string
    enum: ["STATUS", "BRANCH", "CHECKOUT", "ADD", "COMMIT", "PUSH", "PULL", "LOG"]
    description: "Git operation to perform"
  params:
    type: string
    description: >
      Arguments for the command.
      Examples: branch name for CHECKOUT, file path for ADD, message for COMMIT, remote/branch for PUSH.
---

# Instructions

You are an External Contributor managing version control. Think before you commit.

## Operation Reference
| Action | Command Generated | Use When |
|---|---|---|
| STATUS | `git status` | Always run first to understand current state |
| BRANCH | `git branch {params}` | List or create branches |
| CHECKOUT | `git checkout {params}` | Switch branch or create new (`-b fix/name`) |
| ADD | `git add {params}` | Stage specific files or all changes (`.`) |
| COMMIT | `git commit -m "{params}"` | Save staged changes with descriptive message |
| PUSH | `git push {params}` | Upload commits to remote |
| PULL | `git pull {params}` | Sync from remote |
| LOG | `git log -n 5 {params}` | Inspect recent 5 commits |

## Commit Message Convention
feat: add playlist sharing endpoint
fix: resolve null pointer in track upload
chore: update dependencies to latest stable
docs: add API usage examples to README

## Security Guard
```python
from tools.shell_executor import ShellExecutor

action = params.get("action", "STATUS").upper()
arg = params.get("params", "")

cmd_map = {
    "STATUS": "git status",
    "BRANCH": f"git branch {arg}",
    "CHECKOUT": f"git checkout {arg}",
    "ADD": f"git add {arg}",
    "COMMIT": f"git commit -m \"{arg}\"",
    "PUSH": f"git push {arg}",
    "PULL": f"git pull {arg}",
    "LOG": f"git log -n 5 {arg}"
}

git_cmd = cmd_map.get(action, "git status")

# Security validation
from utils.security import SecurityShield
validation = SecurityShield.validate_cli_command(git_cmd)
if validation["status"] == "blocked":
    return {"status": "error", "message": validation["reason"]}

result = await ShellExecutor.execute(git_cmd)
return {
    "status": "success" if result["success"] else "error",
    "message": "Git execution complete.",
    "data": result
}
```

## Professional Workflow Pattern
STATUS         → Understand current state
CHECKOUT -b    → Create isolated branch
[make changes via coder skill]
ADD .          → Stage all changes
COMMIT         → Commit with clear message
PUSH           → Upload to remote