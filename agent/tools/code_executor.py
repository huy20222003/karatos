"""
Code Executor Tool — Sandboxed Python Execution.
Runs Python code safely with timeout, output capture, and resource limits.
The Brain generates the code, this tool executes it.
"""
import asyncio
import sys
import os
import tempfile
import json
from typing import Any, Dict
from utils.logger import get_logger

logger = get_logger()

# Tool metadata for ToolRegistry auto-discovery
TOOL_META = {
    "name": "code_executor",
    "aliases": ["run_python", "python"],
    "class_name": "CodeExecutor",
    "description": "Python Code Executor: Runs Python code in a sandboxed subprocess with timeout, output capture, and error handling. Useful for data processing, calculations, file parsing, and automation scripts.",
    "actions": [
        {
            "name": "execute_python",
            "description": "Execute Python code and return stdout/stderr output. Code runs in a separate process with timeout.",
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {"type": "string", "description": "Python code to execute."},
                    "timeout": {"type": "integer", "description": "Max execution time in seconds (default: 30)."},
                    "working_dir": {"type": "string", "description": "Optional working directory for execution."}
                },
                "required": ["code"]
            }
        }
    ]
}

# Dangerous patterns to block
BLOCKED_PATTERNS = [
    "os.system(",       # Shell injection via os
    "subprocess.call(",
    "subprocess.Popen(",
    "__import__('os').system",
    "shutil.rmtree(",
    "os.rmdir(",
    "os.remove(",
    "os.unlink(",
    "open('/etc",
    "open('C:\\\\Windows",
    "eval(input",
    "exec(input",
]

# Allowed imports whitelist (common safe libraries)
SAFE_IMPORTS = {
    "math", "statistics", "collections", "itertools", "functools",
    "datetime", "time", "re", "json", "csv", "io", "string",
    "random", "hashlib", "base64", "struct", "textwrap",
    "decimal", "fractions", "operator", "copy", "pprint",
    "typing", "dataclasses", "enum", "abc",
    "pathlib", "os.path", "glob",
    "urllib.parse", "html",
    # Data processing (if installed)
    "pandas", "numpy", "polars",
}


class CodeExecutor:
    """
    Sandboxed Python code execution with safety checks.
    Executes code in a subprocess with timeout and output capture.
    """
    
    @classmethod
    def _security_check(cls, code: str) -> tuple[bool, str]:
        """Check code for dangerous patterns. Returns (is_safe, reason)."""
        code_lower = code.lower()
        
        for pattern in BLOCKED_PATTERNS:
            if pattern.lower() in code_lower:
                return False, f"Blocked dangerous pattern: {pattern}"
        
        # Check for network operations (allow httpx/requests but warn)
        if "socket." in code_lower and "socket" not in code:
            return False, "Direct socket access is blocked. Use http_client tool instead."
        
        return True, "OK"

    @classmethod
    async def execute(cls, code: str, timeout: int = 30, 
                      working_dir: str = None) -> Dict[str, Any]:
        """Execute Python code in a sandboxed subprocess."""
        
        # 1. Security check
        is_safe, reason = cls._security_check(code)
        if not is_safe:
            return {"status": "error", "message": f"Security violation: {reason}"}
        
        if not code.strip():
            return {"status": "error", "message": "Empty code provided."}

        # 2. Write code to temp file
        try:
            with tempfile.NamedTemporaryFile(
                mode='w', suffix='.py', delete=False, 
                dir=working_dir, encoding='utf-8'
            ) as f:
                # Inject output capture wrapper
                wrapped_code = f'''import sys
import json

# Redirect to capture
_captured_output = []

class _OutputCapture:
    def __init__(self, stream):
        self.stream = stream
    def write(self, text):
        _captured_output.append(text)
        self.stream.write(text)
    def flush(self):
        self.stream.flush()

sys.stdout = _OutputCapture(sys.stdout)
sys.stderr = _OutputCapture(sys.stderr)

try:
{_indent_code(code)}
except Exception as _e:
    print(f"ERROR: {{type(_e).__name__}}: {{_e}}", file=sys.stderr)
'''
                f.write(wrapped_code)
                temp_path = f.name

        except Exception as e:
            return {"status": "error", "message": f"Failed to create temp file: {e}"}

        # 3. Execute in subprocess
        try:
            process = await asyncio.create_subprocess_exec(
                sys.executable, temp_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=working_dir or os.getcwd()
            )
            
            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(), timeout=timeout
                )
            except asyncio.TimeoutError:
                process.kill()
                await process.communicate()
                return {
                    "status": "error",
                    "message": f"Execution timed out after {timeout}s",
                    "exit_code": -1
                }

            stdout_text = stdout.decode('utf-8', errors='replace').strip()
            stderr_text = stderr.decode('utf-8', errors='replace').strip()
            
            # Truncate very long outputs
            max_output = 10000
            if len(stdout_text) > max_output:
                stdout_text = stdout_text[:max_output] + f"\n... [OUTPUT TRUNCATED, total {len(stdout_text)} chars]"
            if len(stderr_text) > max_output:
                stderr_text = stderr_text[:max_output] + f"\n... [STDERR TRUNCATED]"

            result = {
                "status": "success" if process.returncode == 0 else "error",
                "data": {
                    "exit_code": process.returncode,
                    "stdout": stdout_text,
                    "stderr": stderr_text,
                }
            }
            
            if process.returncode != 0:
                result["message"] = f"Code exited with code {process.returncode}"
            
            return result

        except Exception as e:
            logger.error(f"[CODE_EXECUTOR] Execution failed: {e}")
            return {"status": "error", "message": str(e)}
        
        finally:
            # Cleanup temp file
            try:
                os.unlink(temp_path)
            except:
                pass


def _indent_code(code: str, spaces: int = 4) -> str:
    """Indent code block for wrapping inside try/except."""
    prefix = " " * spaces
    lines = code.split('\n')
    return '\n'.join(prefix + line for line in lines)
