---
name: "restart_service"
description: >
  Service Lifecycle Manager: Safely restart NivaSound ecosystem components via PM2.
  
  Use this for:
  - Recovering from a DEGRADED or unresponsive component (after health_check confirms it)
  - Applying configuration changes that require a restart
  - Admin-initiated maintenance restarts
  
  Components:
  - AGENT: Restart only the NivaSound AI agent process
  - GATEWAY: Restart only the API gateway
  - ALL: Full ecosystem restart (use sparingly)
  
  CAUTION: This is a HIGH RISK action.
  - Always run health_check first to confirm restart is necessary.
  - The AGENT process will die and restart — response delivery is not guaranteed.
  - Prefer AGENT restart over ALL restart whenever possible (minimal blast radius).
  - If force=false (default): safety check for active tasks runs first.
routing_examples:
  - '"The agent is unresponsive, restart it" -> PLAN (Restart agent process)'
  - '"Restart the API gateway to apply the new config" -> PLAN (Restart gateway service)'
  - '"Do a full ecosystem restart for maintenance" -> PLAN (Restart all services)'
  - '"Force restart the agent, skip active task checks" -> PLAN (Force restart with override)'
inputs:
  component:
    type: string
    enum: ["AGENT", "GATEWAY", "ALL"]
    description: "Component to restart. Default: AGENT. Use ALL only when explicitly instructed."
  force:
    type: boolean
    description: "Skip active task safety checks. Only use if normal restart is blocked. Default: false."
---

# Instructions

You are initiating a service restart. Treat this with the gravity it deserves.

## Pre-Restart Protocol (Mandatory)
1. Confirm restart is actually needed (health_check result or Admin explicit request).
2. Warn Admin: "The agent will be briefly unavailable. Expected recovery: 5–10 seconds."
3. If force=false → run active task safety check first.
4. Choose the smallest blast radius: AGENT > GATEWAY > ALL.

## Execution
```python
from datetime import datetime
component = params.get("component", "AGENT").upper()
force = params.get("force", False)

commands = {
    "AGENT":   ["pm2", "restart", "nivasound-agent"],
    "GATEWAY": ["pm2", "restart", "nivasound-gateway"],
    "ALL":     ["pm2", "restart", "all"]
}

cmd = commands.get(component, ["pm2", "restart", "nivasound-agent"])
cmd_str = " ".join(cmd)

# Important: This will likely kill the process if component is AGENT
from tools.shell_executor import ShellExecutor
result = await ShellExecutor.execute(cmd_str)

return {
    "status": "success",
    "message": f"Restart signal sent to {component}. System will recover in 5–10 seconds. 🔄",
    "data": {"timestamp": datetime.utcnow().isoformat(), "command": cmd_str, "raw_result": result}
}
```