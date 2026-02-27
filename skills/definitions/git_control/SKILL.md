---
name: "git_control"
version: "2.0"
description: >
  Git Version Control Manager: Perform Git operations for external repositories.

  Use this for:
  - Checking repository status
  - Creating/switching branches
  - Staging, committing, and pushing changes
  - Viewing commit history
routing_examples:
  - '"Check the current state of the repository" -> PLAN (Git status)'
  - '"Create a new branch for the feature" -> PLAN (Git branch)'
  - '"Commit changes with a descriptive message" -> PLAN (Git commit)'
  - '"Push code to remote" -> PLAN (Git push)'
  - '"Kiểm tra trạng thái git" -> PLAN (Git status)'
inputs:
  action:
    type: string
    enum: ["STATUS", "BRANCH", "CHECKOUT", "ADD", "COMMIT", "PUSH", "PULL", "LOG"]
    description: "Git operation to perform."
  params:
    type: string
    description: "Arguments for the command."
outputs:
  success:
    type: object
    fields:
      status: "success"
      output: "Git command output"
      action: "Action performed"
  error:
    type: object
    fields:
      status: "error"
      message: "Git error message"
required_capabilities:
  - type: "shell_execution"
    description: "Uses shell to run git commands"
tags: ["git", "version-control", "development"]
---

# Instruction: Git Version Control Manager

Think before you commit. Understand before you branch.

## Procedure

1. **Orientation**: Always run `git status` first
2. **Branch**: Use `checkout -b` for isolated work
3. **Stage**: Add specific files, avoid blanket `git add .`
4. **Commit**: Use conventional commit format (`feat:`, `fix:`, `docs:`)
5. **Sync**: Push/pull to interact with remotes
6. **Verify**: Check status/log after each operation

## Validation Rules

| Rule | Check | Action on Fail |
|------|-------|----------------|
| Branch Safety | Never commit directly to main | Create feature branch |
| No Secrets | .env files must not be staged | Remove from staging |
| Clean State | Check status before operations | Resolve conflicts first |

## Error Handling

| Error | Cause | Recovery |
|-------|-------|----------|
| Merge Conflict | Divergent branches | Show conflict details, ask user |
| Push Rejected | Remote has newer changes | Pull first, then push |
| Detached HEAD | Checkout to commit hash | Create branch from current state |

## Constraints
- **NEVER** commit to `main` directly without confirmation
- **NEVER** stage secrets or `.env` files
- Always verify with LOG or STATUS after operations

## Success Criteria
- [x] Git operation completed successfully
- [x] Repository in clean state after operation
