---
name: "terminal_execute"
enabled: true
version: "2.0"
description: >
  Terminal Command Executor: Run shell commands on the host system.
  The Brain generates the appropriate commands; this skill provides execution.

  Use this for:
  - Running system commands (ls, cat, grep, etc.)
  - Installing packages and managing dependencies
  - Process management and system administration
  - Script execution
routing_examples:
  - '"Run df -h to check disk space" -> PLAN (Execute terminal command)'
  - '"List files in the project directory" -> PLAN (Execute terminal command)'
  - '"Install numpy via pip" -> PLAN (Execute terminal command)'
  - '"Chạy lệnh kiểm tra dung lượng ổ đĩa" -> PLAN (Execute terminal command)'
inputs:
  command:
    type: string
    description: "The shell command to execute."
  timeout:
    type: integer
    description: "Max execution time in seconds. Default: 30."
outputs:
  success:
    type: object
    fields:
      status: "success"
      stdout: "Command output"
      exit_code: "Process exit code (0 = success)"
  error:
    type: object
    fields:
      status: "error"
      stderr: "Error output"
      exit_code: "Non-zero exit code"
required_capabilities:
  - type: "shell_execution"
    description: "Direct shell command execution"
tags: ["terminal", "shell", "command", "system"]
---

# Instruction: Terminal Command Executor

Execute precisely. Never run destructive commands without confirmation.

## Procedure

1. **Validate**: Check command against security rules
2. **Execute**: Run the command via shell executor
3. **Capture**: Collect stdout, stderr, and exit code
4. **Report**: Present results clearly to user

## Validation Rules

| Rule | Check | Action on Fail |
|------|-------|----------------|
| Not Destructive | No rm -rf, format, or system wipes | Block and warn |
| Not Agent Source | Must not modify agent code | Block |
| Timeout Set | Command has reasonable timeout | Default to 30s |

## Error Handling

| Error | Cause | Recovery |
|-------|-------|----------|
| Timeout | Command runs too long | Kill process, report |
| Permission Denied | Insufficient privileges | Report and suggest elevation |
| Command Not Found | Tool not installed | Suggest installation |

## Constraints
- Never execute commands that could destroy the host system
- Respect security rules configured in agent settings
- Timeout all long-running commands

## Success Criteria
- [x] Command executed successfully
- [x] Output captured and reported
- [x] No security violations
