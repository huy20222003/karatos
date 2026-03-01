---
name: "web_search"
enabled: true
version: "2.0"
description: >
  Information Retrieval Engine: Search the web for quick facts, prices, news, or general knowledge.

  WHEN TO USE:
  - Current prices, exchange rates, statistics
  - Quick factual lookups
  - Latest news and events
  - When the answer is likely in a search snippet

  WHEN NOT TO USE:
  - Deep multi-source research → use web_research
  - Interacting with a website → use browser_control
routing_examples:
  - '"Find information about the current gold price" -> PLAN (Quick web search)'
  - '"Search for the latest AI news" -> PLAN (Quick web search)'
  - '"Who won the championship last night?" -> PLAN (Quick web search)'
  - '"Giá Bitcoin hiện tại là bao nhiêu?" -> PLAN (Quick web search)'
inputs:
  query:
    type: string
    description: "The search query to execute."
  max_results:
    type: integer
    description: "Maximum number of results to return. Default: 5."
outputs:
  success:
    type: object
    fields:
      status: "success"
      results: "List of search results with titles, snippets, URLs"
      answer: "Direct answer if available"
  error:
    type: object
    fields:
      status: "error"
      message: "Search failure reason"
required_capabilities:
  - type: "web_search"
    description: "Needs search tool for executing web queries"
tags: ["search", "web", "facts", "news"]
---

# Instruction: Web Data Retriever

Execute searches quickly, securely, and accurately.

## Procedure

1. **Extract Query**: Identify the core search terms from user's request
2. **Execute Search**: Run the search query
3. **Analyze Results**: Read the snippets and answers provided
4. **Synthesize**: Provide a concise answer with sources

## Validation Rules

| Rule | Check | Action on Fail |
|------|-------|----------------|
| Query Not Empty | Search terms provided | Ask for clarification |
| Results Available | At least 1 result returned | Report no results found |

## Error Handling

| Error | Cause | Recovery |
|-------|-------|----------|
| No Results | Query too specific or misspelled | Suggest broader terms |
| Rate Limited | Too many requests | Wait and retry |

## Constraints
- Never fabricate data if the search provides no results
- If the query is ambiguous, ask for clarification
- Prefer direct answers from featured snippets

## Success Criteria
- [x] Search executed successfully
- [x] Relevant results returned
- [x] Concise answer provided with sources
