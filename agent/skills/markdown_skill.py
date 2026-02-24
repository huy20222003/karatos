import os
import re
import yaml
import asyncio
from typing import Any, Dict, Optional
from utils.logger import get_logger

logger = get_logger()

class MarkdownSkill:
    """
    Represents a skill defined in a Markdown file.
    Can execute Python or Shell code blocks embedded in the file.
    """
    
    def __init__(self, file_path: str):
        self.file_path = file_path
        self.name = ""
        self.description = ""
        self.input_schema = {}
        self.routing_examples = []
        self.code_blocks = []
        self._parse_file()
        
    def _parse_file(self):
        """Parse the markdown file to extract metadata and code."""
        if not os.path.exists(self.file_path):
            raise FileNotFoundError(f"Skill file not found: {self.file_path}")
            
        with open(self.file_path, 'r', encoding='utf-8') as f:
            content = f.read()
            
        # 1. Parse YAML Frontmatter
        frontmatter_match = re.search(r'^---\s*\n(.*?)\n---\s*\n', content, re.DOTALL)
        if frontmatter_match:
            try:
                metadata = yaml.safe_load(frontmatter_match.group(1))
                self.name = metadata.get("name", "unnamed_skill")
                self.description = metadata.get("description", "")
                # Optional: Input schema in frontmatter
                self.input_schema = metadata.get("inputs", {})
                self.routing_examples = metadata.get("routing_examples", [])
            except yaml.YAMLError as e:
                logger.error(f"[MarkdownSkill] Error parsing frontmatter in {self.file_path}: {e}")
        
        # 2. Extract Code Blocks from Implementation/Execution sections
        # We look for blocks specifically after certain headers to avoid capturing templates in instructions.
        # We prioritize 'Execution' over 'Implementation' if both exist.
        
        # Identify code block boundaries to ignore headers inside them
        code_block_boundaries = []
        for cb_match in re.finditer(r'```.*?```', content, re.DOTALL):
            code_block_boundaries.append((cb_match.start(), cb_match.end()))
            
        # Split by any header at any level (#, ##, ###) but only if NOT inside a code block
        header_pattern = re.compile(r'^#+\s+(.*)', re.MULTILINE)
        all_header_matches = header_pattern.finditer(content)
        
        headers = []
        for h_match in all_header_matches:
            is_inside_code = any(start <= h_match.start() <= end for start, end in code_block_boundaries)
            if not is_inside_code:
                headers.append(h_match)
        
        sections = {}
        last_pos = 0
        last_header = "START"
        
        for match in headers:
            sections[last_header] = content[last_pos:match.start()]
            last_header = match.group(1).strip().lower()
            last_pos = match.end()
        sections[last_header] = content[last_pos:]
        
        # Determine which section to use for code extraction
        exec_content = ""
        if "execution" in sections:
            exec_content = sections["execution"]
        elif "implementation" in sections:
            exec_content = sections["implementation"]
        else:
            exec_content = content # Fallback
            
        code_pattern = re.compile(r'```(\w+)\n(.*?)```', re.DOTALL)
        matches = code_pattern.findall(exec_content)
        
        for lang, code in matches:
            lang = lang.lower().strip()
            if lang in ['python', 'py']:
                self.code_blocks.append({"type": "python", "code": code})
            elif lang in ['bash', 'sh', 'shell']:
                self.code_blocks.append({"type": "shell", "code": code})
                
    async def execute(self, params: Dict[str, Any]) -> Any:
        """
        Execute the skill.
        Executes ALL code blocks in order, sharing a context dictionary.
        """
        if not self.code_blocks:
            return {"status": "error", "message": f"No executable code found in skill {self.name}"}
            
        # Initialize Shared Context
        # Context includes input params AND can be modified by blocks
        context = params.copy()
        block_results = []
        
        logger.debug(f"[MarkdownSkill] Executing {self.name} with {len(self.code_blocks)} steps...")
        
        try:
            for i, block in enumerate(self.code_blocks):
                code_type = block["type"]
                code = block["code"]
                
                logger.debug(f"[MarkdownSkill] Step {i+1}/{len(self.code_blocks)} ({code_type})")
                
                if code_type == "python":
                    res = await self._execute_python(code, context)
                elif code_type == "shell":
                    res = await self._execute_shell(code, context)
                else:
                    res = {"status": "error", "message": f"Unsupported code type: {code_type}"}
                
                block_results.append(res)
                
                # Update context with the last result if it's a dict
                if isinstance(res, dict):
                    context[f"step_{i+1}_result"] = res
                    # If step failed, we might want to stop (standard behavior)
                    if res.get("status") == "error":
                        break
            
            # Final result is the result of the LAST block, or a summary
            final_res = block_results[-1] if block_results else {"status": "success"}
            if isinstance(final_res, dict):
                 final_res["steps_count"] = len(block_results)
                 
            return final_res

        except Exception as e:
            logger.error(f"[MarkdownSkill] Execution failed: {e}")
            return {"status": "error", "message": str(e)}
            
    async def _execute_python(self, code: str, context: dict) -> Any:
        """Execute python code in a local namespace with shared context."""
        from skills.registry import get_skill_registry
        from utils.security import SecurityShield
        import asyncio
        import json
        
        from utils.logger import get_logger
        from pathlib import Path
        
        registry = get_skill_registry()
        # 'params' is provided for backward compatibility, but 'context' is the future
        locals_dict = {
            "params": context, 
            "context": context,
            "result": None,
            "registry": registry,
            "security": SecurityShield,
            "asyncio": asyncio,
            "json": json,
            "print": print,
            "logger": logger,
            "get_logger": get_logger,
            "Path": Path
        }
        
        try:
            wrapped_code = (
                "async def _skill_main():\n" +
                "\n".join(["    " + line for line in code.splitlines()]) +
                "\n"
            )
            
            exec(wrapped_code, locals_dict)
            
            if "_skill_main" in locals_dict:
                function_result = await locals_dict["_skill_main"]()
                if function_result is not None:
                    return function_result
            
            # If function result is None, check for 'result' variable
            return locals_dict.get("result", {"status": "success"})

        except Exception as e:
            logger.warning(f"[MarkdownSkill] Python execution failed: {e}")
            raise e

    async def _execute_shell(self, code: str, context: dict) -> Any:
        """Execute shell code with variable substitution and security checks."""
        from utils.security import SecurityShield
        
        # 1. Variable Substitution from context
        # Pattern: {{var_name}}
        for k, v in context.items():
            pattern = f"{{{{{k}}}}}"
            if pattern in code:
                code = code.replace(pattern, str(v))
        
        # 2. SECURITY: Sanitize the command
        sanitized_code = SecurityShield.sanitize_text(code)
        
        # 3. SECURITY: Analyze risk (prevent destructive commands)
        risk_report = SecurityShield.analyze_risk(sanitized_code)
        if not risk_report["safe"]:
             return {"status": "error", "message": f"Security Shield blocked unsafe shell command: {risk_report['reasons']}"}


        logger.info(f"[MarkdownSkill] Running sanitized shell: {sanitized_code}")

        proc = await asyncio.create_subprocess_shell(
            sanitized_code,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()
        
        if proc.returncode == 0:
            return {"status": "success", "output": stdout.decode().strip()}
        else:
            return {"status": "error", "error": stderr.decode().strip(), "code": proc.returncode}

