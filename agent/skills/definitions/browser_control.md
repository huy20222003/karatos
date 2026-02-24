---
name: "navigate"
description: >
  Autonomous Browser Operator: Physically interact with any website or web application.
  Use this when the task requires DOING something on a page — not just reading it.
  
  WHEN TO USE:
  - Filling and submitting forms (registration, login, data entry)
  - Clicking buttons, navigating menus, triggering UI actions
  - Extracting structured data from dynamic pages (JavaScript-rendered content)
  - Performing multi-step web workflows (e.g., checkout, OAuth, dashboard interactions)
  
  WHEN NOT TO USE:
  - Simple fact retrieval → use WEB:SEARCH instead
  - Reading a static article → use WEB:RESEARCH instead
  
  Internally uses Playwright + Semantic Snapshot for precise, reliable element targeting.
routing_examples:
  - '"Fill out the registration form on the website and submit it" -> PLAN (Form submission via browser)'
  - '"Log in to the admin dashboard and export the user list" -> PLAN (Multi-step browser workflow)'
  - '"Scrape the product listing from this dynamic page" -> PLAN (Dynamic content extraction)'
  - '"Click the approve button on the pending order" -> PLAN (UI interaction on web app)'
inputs:
  url:
    type: string
    description: "Full destination URL including protocol (e.g., https://example.com)"
  task:
    type: string
    description: >
      Precise description of what to accomplish on the page.
      Be specific: 'Fill registration form with provided data and submit' is better than 'register'.
---

# Instructions

You are the Browser Motor Neuron of {bot_name}. Execute this task with precision and care.

## Pre-Execution Checklist
1. SECURITY: URL is validated by SecurityShield (SSRF protection). If blocked → report clearly, do not retry.
2. UNDERSTAND: Parse the `task` fully before touching the page. Know what success looks like.
3. NAVIGATE: Use `semantic_snapshot` (Accessibility Tree) to understand page structure.
4. ACT: Use selectors from `interactive_map` for 100% targeting accuracy.

## Execution Principles
- Prefer semantic selectors (role, label) over fragile CSS paths.
- Batch related actions into arrays. Navigation-triggering actions are always LAST.
- If the page appears broken → use `network` or `console` forensics before retrying.
- Never `fill` a `<button>` or `<a>` element. Always `click` them.
- Complete ALL form fields before submitting. Never submit a partial form.

## Execution
```python
from datetime import datetime
import time
from tools.browser_subagent import browser_subagent
from utils.security import SecurityShield

url = params.get("url")
task = params.get("task", "Explore the page and summarize content")

if not url:
    return {"status": "error", "message": "Target URL is required for navigation."}

if not SecurityShield.validate_url(url):
    return {"status": "error", "message": "URL blocked by Security Shield (SSRF Protection)."}

recording_name = f"web_nav_{int(time.time())}"
try:
    result = await browser_subagent(
        TaskName="Web Interaction",
        Task=f"Go to {url} and perform: {task}",
        RecordingName=recording_name
    )
    
    status = result.get("status", "success")
    return {
        "status": status,
        "message": "WEB_NAVIGATION_COMPLETE" if status == "success" else "WEB_NAVIGATION_FAILED",
        "data": {"url": url, "task": task, "result": result, "timestamp": datetime.utcnow().isoformat()}
    }
except Exception as e:
    return {"status": "error", "message": f"Navigation failed: {e}"}
```