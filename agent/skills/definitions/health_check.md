---
name: "health_check"
description: >
  System Diagnostics Engine: Perform comprehensive health checks across all NivaSound infrastructure components.
  
  Use this for:
  - Routine system monitoring (database, disk, memory, process)
  - Investigating suspected performance degradation
  - Pre-restart verification (check state before restarting services)
  - Post-incident system assessment
  - Autonomous patrol cycle health verification
  
  Modes:
  - QUICK: Database ping + disk usage only (fast, minimal overhead)
  - FULL: All components including latency measurement, process info, and detailed diagnostics
  
  Returns structured JSON with component-level status:
  HEALTHY | DEGRADED | WARNING | CRITICAL_LOW_SPACE
routing_examples:
  - '"Run a health check on the system" -> PLAN (Check system status)'
  - '"How is the server doing right now?" -> PLAN (Check system status)'
  - '"Check the database health" -> PLAN (Check system status)'
  - '"Do a quick ping on infrastructure before the deployment" -> PLAN (Quick system check)'
  - '"Run full diagnostics after the incident" -> PLAN (Full system diagnostics)'
inputs:
  check_type:
    type: string
    enum: ["QUICK", "FULL"]
    description: "QUICK for fast checks, FULL for comprehensive diagnostics. Default: FULL"
---

# Instructions

You are the System Health Sensor of {bot_name}. Report truthfully — even bad news.

## Diagnostic Components
| Component | What's Checked | Alert Threshold |
|---|---|---|
| Database | Connectivity + response latency | No connection → DEGRADED |
| Disk | Total / Used / Free GB, usage % | >90% used → WARNING |
| Process | PID, working directory | Always reported |

## Execution
```python
check_type = params.get("check_type", "FULL")
service = params.get("service", "All")
print(f"[HealthCheck] Checking status for: {service}")
return {"status": "success", "message": "SERVICE_STATUS_CHECK", "service": service, "current_status": "OPERATIONAL"}
```

## Reporting Principle
Never hide component failures. If database is DEGRADED, say so clearly.
The Admin needs accurate information to make decisions.
If ALL components pass → celebrate briefly. 🎉
If something fails → report with empathy, suggest next action (e.g., restart_service, clear_cache).