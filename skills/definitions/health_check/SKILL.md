---
name: "health_check"
version: "2.0"
description: >
  System Diagnostics Engine: Perform comprehensive health checks across all infrastructure components.

  Use this for:
  - Routine system monitoring (database, disk, memory, process)
  - Investigating suspected performance degradation
  - Pre-restart verification
  - Post-incident assessment
routing_examples:
  - '"Run a health check on the system" -> PLAN (Check system status)'
  - '"How is the server doing right now?" -> PLAN (Check system status)'
  - '"Check the database health" -> PLAN (Check system status)'
  - '"Run full diagnostics after the incident" -> PLAN (Full system diagnostics)'
  - '"Kiểm tra sức khỏe hệ thống" -> PLAN (Check system status)'
inputs:
  check_type:
    type: string
    enum: ["QUICK", "FULL"]
    description: "QUICK for fast checks, FULL for comprehensive diagnostics. Default: FULL"
outputs:
  success:
    type: object
    fields:
      status: "OPERATIONAL | DEGRADED | WARNING | CRITICAL"
      components: "Health status per component"
      recommendations: "Suggested actions if issues found"
  error:
    type: object
    fields:
      status: "error"
      message: "Diagnostic failure reason"
required_capabilities:
  - type: "shell_execution"
    description: "Runs system commands (df, tasklist, pm2 status, etc.)"
  - type: "system_monitoring"
    description: "Needs process monitor for CPU/RAM/disk metrics"
tags: ["monitoring", "diagnostics", "system", "operations"]
---

# Instruction: System Health Sensor

Report truthfully — even bad news.

## Procedure

1. **Gather**: Run system commands to collect metrics
2. **Analyze**: Check each component against thresholds
3. **Diagnose**: Identify any degraded components
4. **Report**: Provide clear status with numbers
5. **Recommend**: Suggest actions if issues found

## Validation Rules

| Rule | Check | Action on Fail |
|------|-------|----------------|
| Disk | Usage < 90% | WARNING status |
| Database | Connection succeeds | DEGRADED status |
| Processes | Critical services running | WARNING status |
| Memory | Available > 10% | WARNING status |

## Error Handling

| Error | Cause | Recovery |
|-------|-------|----------|
| Command Failed | OS command error | Report partial results |
| DB Unreachable | Network/service issue | Mark as CRITICAL |

## Constraints
- Never hide failures
- Be precise with percentages and latency numbers
- QUICK check: disk + process only; FULL check: all components

## Success Criteria
- [x] All requested components checked
- [x] Status reported with precise metrics
- [x] Recommendations provided for any issues
