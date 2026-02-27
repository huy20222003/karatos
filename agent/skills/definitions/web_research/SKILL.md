---
name: "research"
version: "2.0"
description: >
  Web Intelligence Gatherer: Conduct depth-calibrated research from the open web.

  Three depth modes — choose based on task complexity:

  SEARCH (fastest):
    Real-time facts, current prices, breaking news, simple lookups.
  RESEARCH (medium):
    Read and synthesize a specific article, documentation page, or report.
  DEEP_RESEARCH (thorough):
    Multi-source investigation, cross-referencing, contradiction detection.

  Always choose the MINIMUM depth needed. Don't DEEP_RESEARCH a simple fact.
routing_examples:
  - '"What is the current exchange rate for USD to VND?" -> PLAN (Quick web search)'
  - '"Summarize what this documentation says about OAuth 2.0" -> PLAN (Medium web research)'
  - '"Compare PostgreSQL and MySQL with a full analysis" -> PLAN (Deep web research)'
  - '"Tìm giá Bitcoin hiện tại" -> PLAN (Quick web search)'
  - '"Nghiên cứu best practices cho REST API security" -> PLAN (Deep web research)'
inputs:
  topic:
    type: string
    description: "The subject, question, or URL to research. Be specific."
  depth:
    type: string
    enum: ["SEARCH", "RESEARCH", "DEEP_RESEARCH"]
    description: "Research depth. Match to task complexity. Default: SEARCH."
outputs:
  success:
    type: object
    fields:
      status: "success"
      findings: "Research results with source attribution"
      depth_used: "Which depth mode was applied"
      sources: "List of URLs consulted"
  error:
    type: object
    fields:
      status: "error"
      message: "Research failure reason"
required_capabilities:
  - type: "web_search"
    description: "Needs search tool for finding relevant sources"
  - type: "web_scraping"
    description: "May need scraper for deep content extraction"
  - type: "browser_interaction"
    description: "May need browser for JS-rendered pages"
tags: ["research", "web", "search", "analysis", "intelligence"]
---

# Instruction: Web Intelligence Gatherer

Gather information efficiently, accurately, and thoroughly.

## Procedure

### SEARCH Mode (Fast Facts)
1. Execute web search for the query
2. Extract direct answer from snippets
3. Return answer with top sources

### RESEARCH Mode (Synthesis)
1. Search for most relevant sources
2. Select top URL and extract in-depth content
3. Summarize key points for the user's question

### DEEP_RESEARCH Mode (Comprehensive)
1. Break topic into 3 specific sub-queries
2. Search for each sub-query
3. Aggregate all findings
4. Cross-reference data, identify contradictions
5. Generate structured report with source attribution

## Validation Rules

| Rule | Check | Action on Fail |
|------|-------|----------------|
| Depth Appropriate | Match depth to query complexity | Suggest correct depth |
| Sources Available | At least 1 relevant source found | Report no results |
| Accuracy | Cross-reference critical claims | Flag unverified claims |

## Error Handling

| Error | Cause | Recovery |
|-------|-------|----------|
| No Results | Topic too niche or poorly formatted | Suggest refined query |
| Source Unavailable | URL blocked or down | Try alternative sources |
| Contradictions | Sources disagree | Present both sides |

## Constraints
- Cite sources whenever possible
- Flag contradictions between different results
- Prioritize official documentation for technical queries
- Never fabricate confidence if results are inconclusive

## Success Criteria
- [x] Information gathered at appropriate depth
- [x] Sources cited and attributed
- [x] Answer directly addresses user's question
