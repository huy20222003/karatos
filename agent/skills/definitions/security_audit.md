---
name: "security_audit"
description: >
  Security Intelligence Reviewer: Surface and analyze security incidents from the audit trail.
  
  Use this for:
  - Investigating suspicious user activity flagged during autonomous patrol
  - Reviewing recent SSRF attempts, injection attacks, or blocked requests
  - Generating security reports for Admin review
  - Cross-referencing a specific incident with the broader 24h security picture
  - Autonomous patrol cycle security sweep
  
  Filters automatically for security-relevant events:
  SECURITY | RISK | BLOCK | INJECTION | SSRF
  
  Always covers the last 24 hours. Use `limit` to control result volume.
routing_examples:
  - '"Show me any suspicious activity in the last 24 hours" -> PLAN (Security audit sweep)'
  - '"Have there been any SSRF or injection attempts recently?" -> PLAN (Security incident review)'
  - '"Generate a security report for the Admin" -> PLAN (Security report generation)'
  - '"Something looks off with user activity, audit the logs" -> PLAN (Security investigation)'
inputs:
  limit:
    type: integer
    description: "Number of most recent incidents to surface. Default: 10. Increase for deeper investigation."
---

# Instructions

You are the Security Intelligence Layer of {bot_name}. Report with precision. Never downplay threats.

## Execution
```python
from datetime import datetime
from tools.database_reader import DatabaseReader

limit = params.get("limit", 10)
db = DatabaseReader()
logs = db.get_audit_logs(hours=24)

if not logs:
    return {"status": "success", "message": "All clear in the last 24h. 🛡️", "data": {"total_24h": 0}}

actions = {}
security_incidents = []
for l in logs:
    a = l.get("action", "unknown")
    actions[a] = actions.get(a, 0) + 1
    if "SECURITY" in str(l).upper() or "BLOCK" in str(l).upper() or "FAILED" in str(l).upper():
        security_incidents.append(l)

report_list = security_incidents[:limit]
msg = f"Security audit complete. {len(security_incidents)} incidents in last 24h."
if len(security_incidents) > 10:
    msg = "Elevated incident rate detected. Recommend investigation. " + msg

return {
    "status": "success",
    "message": msg,
    "data": {
        "summary": {"total_24h": len(security_incidents), "view_limit": limit, "top_actions": dict(list(actions.items())[:5])},
        "incidents": report_list,
        "timestamp": datetime.utcnow().isoformat()
    }
}
```