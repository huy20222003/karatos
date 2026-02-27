---
name: "summarize_document"
version: "2.0"
description: >
  Local Document Reader & Summarizer: Extract and summarize content from LOCAL DOCX and PDF files.
  NOT FOR URLs/WEBSITES.

  Use this for:
  - Summarizing research papers, reports, and documents
  - Extracting key information from uploaded files
  - Reading and analyzing document content
routing_examples:
  - '"Tóm tắt file báo cáo.docx" -> PLAN (Summarize Document)'
  - '"Summarize this research paper.pdf" -> PLAN (Summarize Document)'
  - '"What does this document say?" -> PLAN (Read Document)'
  - '"Đọc nội dung file PDF này" -> PLAN (Read Document)'
inputs:
  file_path:
    type: string
    description: "The path to the DOCX or PDF file."
outputs:
  success:
    type: object
    fields:
      status: "success"
      summary: "Concise summary of the document"
      page_count: "Number of pages processed"
      word_count: "Approximate word count"
  error:
    type: object
    fields:
      status: "error"
      message: "Why extraction failed (unsupported format, corrupted, etc.)"
required_capabilities:
  - type: "code_execution"
    description: "Needs Python executor to run document parsing libraries"
  - type: "shell_execution"
    description: "May need shell for file operations"
tags: ["document", "summary", "pdf", "docx", "analysis"]
---

# Instruction: Document Reader & Summarizer

File-First Thinking — validate existence, then extract, then summarize.

## Procedure

1. **Locate**: Identify the file path (explicitly or from context)
2. **Validate**: Check file exists and format is supported (.docx, .pdf)
3. **Extract**: Pull text content from the document
4. **Analyze**: Read the extracted text (up to 8000 characters)
5. **Summarize**: Generate a natural, concise summary in the user's language

## Validation Rules

| Rule | Check | Action on Fail |
|------|-------|----------------|
| File Exists | Path must point to real file | Report file not found |
| Format Supported | Must be .docx or .pdf | Report unsupported format |
| Content Available | Extracted text must be non-empty | Report empty/image-only doc |

## Error Handling

| Error | Cause | Recovery |
|-------|-------|----------|
| File Not Found | Wrong path | Ask user for correct path |
| Corrupted File | Damaged document | Report corruption |
| Image-Only PDF | Scanned document | Inform user, suggest OCR |

## Constraints
- Only `.docx` and `.pdf` are supported
- Mention if document was truncated due to size
- Empathize if file is missing or corrupted

## Success Criteria
- [x] Document content extracted
- [x] Summary generated in user's language
- [x] Page/word count reported
