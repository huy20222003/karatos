---
name: "security_audit"
version: "2.0"
description: >
  Security Intelligence Reviewer: Surface and analyze security incidents from the audit trail.

  Use this for:
  - Investigating suspicious user activity
  - Reviewing SSRF attempts or blocked requests
  - Generating security reports
  - Autonomous patrol cycle sweeps
routing_examples:
  - '"Show me any suspicious activity in the last 24 hours" -> PLAN (Security audit sweep)'
  - '"Have there been any SSRF or injection attempts recently?" -> PLAN (Security incident review)'
  - '"Generate a security report for the Admin" -> PLAN (Security report generation)'
  - '"Kiểm tra bảo mật hệ thống" -> PLAN (Security audit sweep)'
inputs:
  limit:
    type: integer
    description: "Number of most recent incidents to surface. Default: 10."
  hours:
    type: integer
    description: "How far back to look in hours. Default: 24."
outputs:
  success:
    type: object
    fields:
      status: "success"
      incidents: "List of security incidents found"
      summary: "Statistical summary"
      severity: "Overall threat level"
  error:
    type: object
    fields:
      status: "error"
      message: "Audit failure reason"
required_capabilities:
  - type: "shell_execution"
    description: "May need shell to read log files"
  - type: "data_analysis"
    description: "Analyzes patterns in security logs"
tags: ["security", "audit", "monitoring", "compliance"]
---

# Instruction: Security Intelligence Layer

Report with precision. Never downplay threats.

## Procedure

1. **Retrieve**: Collect audit logs from the specified time period
2. **Filter**: Look for keywords: SECURITY, RISK, BLOCK, INJECTION, SSRF, FAILED
3. **Analyze**: Count occurrences, identify patterns, detect anomalies
4. **Classify**: Rate incidents by severity (LOW, MEDIUM, HIGH, CRITICAL)
5. **Report**: Provide structured summary with specific entries

## Validation Rules

| Rule | Check | Action on Fail |
|------|-------|----------------|
| Time Range | Must cover at least last 24 hours | Extend range |
| Data Source | Audit logs accessible | Report access issue |

## Error Handling

| Error | Cause | Recovery |
|-------|-------|----------|
| No Logs Found | Logging not configured | Report configuration gap |
| Partial Data | Some log files missing | Report with available data |

## Constraints
- Always cover at least the last 24 hours
- If incident rates are elevated, recommend deeper investigation
- Never hide potential threats

## Success Criteria
- [x] All relevant time periods scanned
- [x] Incidents classified by severity
- [x] Actionable recommendations provided
