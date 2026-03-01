import re
from typing import Any, Optional, Union
from utils.charts import render_table_to_image
from utils.logger import get_logger

logger = get_logger()

class VisualEnhancer:
    """
    Utility to detect and enhance text responses with visual components (charts/tables).
    Unified logic for both first-time generation and cache restoration.
    """
    
    @staticmethod
    def detect_table(text: str) -> Optional[tuple[list[list[str]], list[str], str]]:
        """
        Detect a table (Markdown or PSQL-style) in text and parse it.
        Returns: (rows, headers) or None
        """
        # 1. Detect Markdown Table (Fast & Safe check)
        # Instead of one giant regex, we look for headers + separator line
        # This is much faster and avoids backtracking hangs
        lines = text.split("\n")
        table_start = -1
        for i, line in enumerate(lines):
            trimmed = line.strip()
            # Relaxed: At least 1 pipe for a 2-column table
            if trimmed.count("|") >= 1 and re.match(r"^\|?[:\s-]+\|?(?:[:\s-]+\|?)*$", trimmed):
                # The line before must be the header and have at least 1 pipe
                if i > 0 and lines[i-1].count("|") >= 1:
                    table_start = i - 1
                    break
        
        if table_start >= 0:
            # Found a potential table
            try:
                header_line = lines[table_start].strip()
                # Simplified to match headers + separator + data lines
                def split_row(row_str):
                    return [c.strip() for c in row_str.strip("|").split("|")]

                headers = split_row(header_line)
                rows = []
                # Find the end of the table (first line without pipes or empty)
                for line in lines[table_start + 2:]:
                    line = line.strip()
                    if not line or "|" not in line:
                        break
                    row = split_row(line)
                    if len(row) > 0:
                        row = (row + [""] * len(headers))[:len(headers)]
                        rows.append(row)
                
                if rows and headers:
                    match_text = "\n".join(lines[table_start : table_start + 2 + len(rows)])
                    return rows, headers, match_text
            except Exception as e:
                pass

        # 2. Detect PSQL-style Table (tabulate 'psql' fmt)
        psql_table_pattern = r"\+[-+]+\+\n(?:\|.*\|\n)+\+[-+]+\+\n(?:\|.*\|\n)+\+[-+]+\+"
        match = re.search(psql_table_pattern, text, re.MULTILINE)
        if match:
            table_text = match.group(0).strip()
            lines = [line.strip() for line in table_text.split("\n") if line.strip()]
            if len(lines) >= 5:
                # Header is at index 1
                headers = [h.strip() for h in lines[1].strip("|").split("|")]
                rows = []
                # Rows start at index 3, skip separators
                for line in lines[3:]:
                    if line.startswith("+"): continue
                    row = [c.strip() for c in line.strip("|").split("|")]
                    row = (row + [""] * len(headers))[:len(headers)]
                    rows.append(row)
                return rows, headers, table_text
            
        # 3. Detect Polars Table
        # Polars format: shape: (R, C) \n ┌─...┐ \n │ col ┆ ... │ \n ... \n └─...┘
        polars_header_pattern = r"shape:\s*\((\d+),\s*(\d+)\)"
        polars_match = re.search(polars_header_pattern, text)
        if polars_match:
            try:
                # Find the box-drawing part
                box_lines = []
                in_box = False
                for line in text.split("\n"):
                    if "┌" in line and "┐" in line:
                        in_box = True
                    if in_box:
                        box_lines.append(line)
                        if "└" in line and "┘" in line:
                            break
                
                if len(box_lines) >= 5:
                    # Polars box structure:
                    # 0: top border ┌───┐
                    # 1: headers    │ id ┆ ... │
                    # 2: separator  │ ---┆ ... │
                    # 3: types      │ str┆ ... │
                    # 4: double sep ╞═══╪ ... ╡
                    # 5+: data      │ ...┆ ... │
                    # n: bottom     └───┘
                    
                    headers = [h.strip() for h in box_lines[1].strip("│").split("┆")]
                    rows = []
                    for line in box_lines[5:-1]:
                        if "│" in line:
                            # Handle wrapped rows (Polars wraps within cells)
                            # Simple approach: if line doesn't have ┆ but has │, it might be a continuation
                            # But Polars usually puts ┆ even in wrapped cells if multiple columns
                            row = [c.strip() for c in line.strip("│").split("┆")]
                            # Align with headers
                            row = (row + [""] * len(headers))[:len(headers)]
                            rows.append(row)
                    
                    if rows and headers:
                        # Reconstruct the exact match text to strip it later
                        match_text = "\n".join(box_lines)
                        return rows, headers, match_text
            except Exception as e:
                pass

        return None

    @staticmethod
    def detect_list(text: str) -> Optional[tuple[list[list[str]], list[str], str]]:
        """
        Detect a long bullet or numbered list and convert to a table for rendering.
        """
        # Improved regex to catch: "- item", "**1.** item", etc.
        list_pattern = r"(?:^|\n)(?:\*\*)?(?:[-*•]|\d+[.)])(?:\*\*)?\s+(.*)"
        matches = re.findall(list_pattern, text)
        
        # Look for 5+ items
        if len(matches) >= 5:
            headers = ["Items"]
            rows = [[m.strip()] for m in matches]
            
            # Find the whole block of matches to strip it later
            all_matches_iter = list(re.finditer(list_pattern, text))
            if all_matches_iter:
                start = all_matches_iter[0].start()
                end = all_matches_iter[-1].end()
                match_text = text[start:end]
                return rows, headers, match_text
        
        return None

    @classmethod
    async def enhance_response(cls, response_data: Union[str, dict], user_message: str = "", skip_visuals: bool = False, language_code: str | None = None) -> dict:
        """
        Takes a response and adds 'photo' and 'caption' if it contains visualizable data.
        Returns a structured response dictionary.
        Now async to support LLM-driven intelligent summarization.
        """
        if skip_visuals:
            return response_data if isinstance(response_data, dict) else {"text": str(response_data)}

        text = response_data if isinstance(response_data, str) else response_data.get("text", "")
        if not text:
            return response_data if isinstance(response_data, dict) else {"text": str(response_data)}

        # 1. Check if already has a photo/image
        if isinstance(response_data, dict) and (response_data.get("photo") or response_data.get("image")):
             if "image" in response_data and not response_data.get("photo"):
                 response_data["photo"] = response_data.pop("image")
             return response_data

        # 2. Try to detect and render visual data
        try:
            result = cls.detect_table(text)
            title = "NivaSound Data Report"
            
            if not result:
                result = cls.detect_list(text)
                title = "NivaSound Summary"
            elif "shape:" in text: # This condition should be part of the table detection logic, not here.
                                   # It's likely a remnant from a previous edit.
                title = "NivaSound Data Analysis"
            
            if result:
                rows, headers, match_text = result
                
                # NGO FIX: Strip Markdown bold tags (**) from values before rendering to image
                # Matplotlib tables don't render Markdown, so tags appear literally (ugly)
                def clean_val(v):
                    return str(v).replace("**", "").strip()
                
                clean_headers = [clean_val(h) for h in headers]
                clean_rows = [[clean_val(c) for c in r] for r in rows]

                # NGO FIX: Strict rule - Only generate image if data has at least 3 columns AND 5 rows
                # This prevents generating huge images for tiny or simple datasets.
                non_empty_cols = [h for h in clean_headers if h]
                if len(non_empty_cols) < 3 or len(clean_rows) < 5:
                    logger.debug(f"[VISUALIZER] Data too small ({len(non_empty_cols)} cols, {len(clean_rows)} rows). Skipping image rendering.")
                    return response_data if isinstance(response_data, dict) else {"text": text}

                image_bytes = render_table_to_image(clean_rows, clean_headers, title=title)
                
                if image_bytes:
                    # NGO FIX: Robust text replacement. find() can fail if newlines are mixed (LF vs CRLF).
                    # We use replace with the exact match_text detected.
                    # Since match_text was reconstructed from split lines, we try both possibilities.
                    clean_text = text.replace(match_text, "").strip()
                    if len(clean_text) == len(text): # Replace failed (likely newline mismatch)
                        # Fallback to the find approach but more carefully
                        idx = text.find(match_text.split("\n")[0]) # Find by first line
                        if idx >= 0:
                            intro_text = text[:idx].strip()
                        else:
                            intro_text = ""
                    else:
                        intro_text = clean_text
                    
                    # --- INTELLIGENT SUMMARIZATION ---
                    # We ALWAYS want a summary if it's a visual report
                    try:
                        from core.brain.model import SharedModelProvider
                        from core.brain.prompts.registry import get_prompt_registry
                        from config.settings import settings
                        from utils.language import normalize_language_code, language_for_prompt

                        model = SharedModelProvider.get_model()
                        registry = get_prompt_registry()

                        bot_name = getattr(settings, "bot_name", "Brain")

                        # Determine language hint for the summarizer
                        code = language_code or getattr(settings, "user_language", "vi")
                        lang_val = language_for_prompt(
                            normalize_language_code(code, default="vi"),
                            default="vi",
                        )

                        # NGO FIX: Correct key from data_realm to data + pass language hint
                        summary_prompt = registry.get(
                            "capabilities.data.data_report_summary",
                            data_text=match_text,
                            user_query=user_message,
                            bot_name=bot_name,
                            language=lang_val,
                        )
                        resp = await model.ainvoke(summary_prompt)
                        from core.brain.utils import get_llm_content
                        llm_summary = get_llm_content(resp).strip()
                        
                        if llm_summary:
                            # Combine intro with summary
                            clean_text = f"{intro_text}\n\n{llm_summary}" if intro_text else llm_summary
                        else:
                            clean_text = intro_text or "NivaSound Data Report"
                    except Exception as summarization_error:
                        logger.error(f"[VISUALIZER] Failed to generate LLM summary: {summarization_error}")
                        clean_text = intro_text or f"NivaSound Data Report for {title}"
                    
                    if isinstance(response_data, str):
                        return { "text": clean_text, "photo": image_bytes, "caption": clean_text[:1000] }
                    else:
                        response_data["text"] = clean_text
                        response_data["photo"] = image_bytes
                        response_data["caption"] = clean_text[:1000]
                        return response_data
                         
        except Exception as e:
            logger.error(f"[VISUALIZER] Error enhancing response: {e}")
            
        return response_data if isinstance(response_data, dict) else {"text": text}

async def enhance_response(
    response: Union[str, dict],
    user_message: str = "",
    skip_visuals: bool = False,
    language_code: str | None = None,
) -> dict:
    """Helper function for easy import (Async version)"""
    return await VisualEnhancer.enhance_response(
        response,
        user_message=user_message,
        skip_visuals=skip_visuals,
        language_code=language_code,
    )
