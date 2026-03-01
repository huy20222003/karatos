---
name: "restart_service"
enabled: true
version: "2.0"
description: >
  Service Lifecycle Manager: Safely restart ecosystem components.

  Use this for:
  - Recovering from a DEGRADED or unresponsive component
  - Applying configuration changes
  - Maintenance restarts
routing_examples:
  - '"The agent is unresponsive, restart it" -> PLAN (Restart agent process)'
  - '"Restart the API gateway to apply the new config" -> PLAN (Restart gateway service)'
  - '"Do a full ecosystem restart for maintenance" -> PLAN (Restart all services)'
  - '"Khởi động lại agent" -> PLAN (Restart agent process)'
inputs:
  component:
    type: string
    enum: ["AGENT", "GATEWAY", "ALL"]
    description: "Component to restart. Default: AGENT. Use ALL only when instructed."
  force:
    type: boolean
    description: "Skip active task safety checks. Default: false."
outputs:
  success:
    type: object
    fields:
      status: "success"
      component: "Which component was restarted"
      message: "Restart confirmation"
  error:
    type: object
    fields:
      status: "error"
      message: "Why restart failed"
required_capabilities:
  - type: "shell_execution"
    description: "Needs shell to run PM2/systemctl restart commands"
  - type: "service_management"
    description: "Must check service status before and after restart"
tags: ["operations", "restart", "service", "maintenance"]
---

# Instruction: Service Lifecycle Manager

Treat restarts with gravity. Always verify before and after.

## Procedure

1. **Confirm Need**: Run health_check first or verify explicit admin request
2. **Warn User**: "The agent will be briefly unavailable (5-10s)"
3. **Choose Radius**: Prefer AGENT > GATEWAY > ALL
4. **Pre-Check**: If force=false, ensure no critical tasks are mid-execution
5. **Execute**: Run the appropriate restart command
6. **Verify**: Confirm service came back up

## Validation Rules

| Rule | Check | Action on Fail |
|------|-------|----------------|
| Admin Confirmed | Restart authorized | Request confirmation |
| No Active Tasks | force=false requires idle state | Wait or warn |
| Component Valid | Must be AGENT, GATEWAY, or ALL | Default to AGENT |

## Error Handling

| Error | Cause | Recovery |
|-------|-------|----------|
| Service Won't Stop | Zombie process | Force kill then restart |
| Service Won't Start | Config error | Report error, suggest rollback |

## Constraints
- High risk: The agent process will die and restart
- Guaranteed delivery is not certain after execution

## Success Criteria
- [x] Service restarted successfully
- [x] Service confirmed running after restart
- [x] User notified of outcome
