"""
Document Summarizer Tool
Combines file reading and text summarization for a seamless workflow.
"""
import os
from typing import Any, Dict
from tools.file_reader import FileReader
from tools.summarizer_tool import SummarizerTool
from utils.logger import get_logger

logger = get_logger()

TOOL_META = {
    "name": "document_summarizer",
    "aliases": ["summarize_document", "read_and_summarize"],
    "class_name": "DocumentSummarizer",
    "description": "Chuyên gia tóm tắt: Xử lý file PDF, Word, và văn bản dài để trích xuất ý chính.",
    "author": "Karatos Core",
    "version": "1.1.0",
    "enabled": True,
    "actions": [
        {
            "name": "summarize_document",
            "description": "Read and summarize a document file.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "file_path": {"type": "string", "description": "Absolute path to the LOCAL document file. NO URLs."},
                    "style": {"type": "string", "enum": ["brief", "detailed", "bullet_points"], "description": "Summary style."}
                },
                "required": ["file_path"]
            }
        }
    ]
}

class DocumentSummarizer:
    """Executes the document summarization workflow."""

    @classmethod
    async def execute(cls, file_path: str = "", style: str = "brief", **kwargs) -> Dict[str, Any]:
        """Read a file and then summarize its content."""
        if not file_path:
            return {"status": "error", "message": "Missing 'file_path' parameter."}

        # 1. Read the file
        logger.info(f"[DOC_SUMMARIZER] Step 1: Reading file {file_path}")
        read_result = await FileReader.execute(file_path=file_path)
        
        if read_result.get("status") != "success":
            return read_result

        content = read_result.get("data", {}).get("content", "")
        if not content:
            return {"status": "error", "message": "Document is empty or no text could be extracted."}

        # 2. Summarize the content
        logger.info(f"[DOC_SUMMARIZER] Step 2: Summarizing content ({len(content)} chars)")
        summary_result = await SummarizerTool.execute(text=content, style=style)
        
        if summary_result.get("status") != "success":
            # If summarization fails, at least return the extracted content or a specific error
            return {
                "status": "error", 
                "message": f"Summarization failed: {summary_result.get('message')}",
                "data": {"extracted_content_preview": content[:500]}
            }

        # 3. Combine results
        summary_data = summary_result.get("data", {})
        return {
            "status": "success",
            "data": {
                "summary": summary_data.get("summary"),
                "file_info": read_result.get("data"),
                "style": style
            }
        }
