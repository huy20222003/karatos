---
name: "navigate"
version: "2.0"
description: >
  Autonomous Browser Operator: Physically interact with any website or web application.
  Used for form filling, clicking, multi-step workflows, and dynamic page interactions.

  Use this for:
  - Filling out web forms and submitting data
  - Navigating multi-step workflows (login, registration, checkout)
  - Extracting data from JavaScript-rendered pages
  - Taking screenshots and capturing page state

  DO NOT use for:
  - Simple web searches → use web_search
  - Downloading static content → use web_scraper
routing_examples:
  - '"Fill out the registration form on the website" -> PLAN (Browser navigation)'
  - '"Log in and export the user list" -> PLAN (Browser workflow)'
  - '"Scrape product listing from this dynamic page" -> PLAN (Dynamic extraction)'
  - '"Take a screenshot of the dashboard" -> PLAN (Browser capture)'
  - '"Điền form đăng ký trên trang web" -> PLAN (Browser navigation)'
inputs:
  url:
    type: string
    description: "Full destination URL."
  task:
    type: string
    description: "Precise description of what to accomplish on the page."
outputs:
  success:
    type: object
    fields:
      status: "success"
      actions_taken: "List of browser actions performed"
      final_state: "Description of final page state"
  error:
    type: object
    fields:
      status: "error"
      message: "What went wrong"
required_capabilities:
  - type: "browser_interaction"
    description: "Needs browser automation tool to navigate and interact with web pages"
  - type: "url_validation"
    description: "Must validate URL safety before navigation"
tags: ["browser", "web", "automation", "scraping"]
---

# Instruction: Autonomous Browser Operator

Execute with precision and care. Validate before acting, observe after.

## Context Awareness
- Check if the URL has been visited recently in conversation context
- Consider page load times for dynamic sites
- Be aware of authentication state

## Procedure

1. **Validate**: Ensure the URL is valid, safe, and accessible
2. **Navigate**: Use browser automation to navigate to the URL
3. **Execute Task**: Perform the specified actions on the page
4. **Observe**: Capture the final state and any relevant data
5. **Report**: Synthesize results for the user

## Validation Rules

| Rule | Check | Action on Fail |
|------|-------|----------------|
| URL Format | Must start with http/https | Return error with guidance |
| Page Load | Page must load within 15s | Report timeout error |
| Task Clarity | Task description must be actionable | Ask for clarification |

## Error Handling

| Error | Cause | Recovery |
|-------|-------|----------|
| Timeout | Page slow/unresponsive | Retry once, then report |
| Element Not Found | Selector invalid | Try alternative selectors |
| Auth Required | Login needed | Inform user, attempt login if credentials available |

## Constraints
- Prefer semantic selectors if possible
- Never submit partial or invalid forms
- If the page fails to load, report the console/network errors found

## Success Criteria
- [x] Target page loaded successfully
- [x] All specified actions completed
- [x] Results extracted and reported
