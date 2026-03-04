import asyncio
import subprocess
import re
import shlex
from typing import Dict, Any, Optional
from utils.logger import get_logger
from utils.security import SecurityShield
import os

logger = get_logger()

# Tool metadata for ToolRegistry auto-discovery
TOOL_META = {
    "name": "shell_executor",
    "aliases": ["execute", "bash", "shell", "terminal"],
    "class_name": "ShellExecutor",
    "enabled": True,
    "author": "Karatos Core",
    "version": "1.0.0",
    "description": "System Shell Executor: Runs arbitrary shell commands on the host OS with security validation, timeout control, and output capture. The Brain decides what commands to use based on the OS platform.",
    "actions": [
        {
            "name": "execute",
            "description": "Execute a shell command on the host system. The Brain must determine the correct command syntax for the current OS.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "The shell command to execute."},
                    "timeout": {"type": "integer", "description": "Max execution time in seconds (default: 30)."}
                },
                "required": ["command"]
            }
        }
    ]
}

class ShellExecutor:
    """
    Asynchronous shell command executor for Brain.
    Ensures commands are run with timeouts and output is captured securely.
    """

    # Tokens that are clearly NOT file paths (common flags, operators, etc.)
    _NON_PATH_PATTERNS = re.compile(
        r'^(-{1,2}[a-zA-Z]'   # flags like -r, --verbose
        r'|[|>&;]'            # shell operators
        r'|\d+$'             # pure numbers (e.g., timeout values)
        r'|https?://'         # URLs
        r'|[a-zA-Z]+://)',    # other URI schemes
        re.IGNORECASE
    )

    @staticmethod
    def _resolve_paths_in_command(command: str, cwd: str) -> str:
        """
        Scan tokens in a shell command and convert relative path-like tokens
        to absolute paths based on `cwd`.

        A token is considered a path-like candidate if it:
        - Starts with ./ or ../
        - Contains path separators (/ or \\) but is not a URL or flag
        - Is a bare filename that actually exists on disk relative to cwd

        Tokens that are already absolute paths are left untouched.
        """
        # We use a simple split approach that respects quoted strings
        try:
            tokens = shlex.split(command, posix=False)
        except ValueError:
            # If shlex can't parse (e.g., unmatched quotes), fall back to naive split
            tokens = command.split()

        resolved_parts: list[str] = []
        changed = False

        for token in tokens:
            # Strip surrounding quotes for analysis, but keep them for reconstruction
            stripped = token.strip('"').strip("'")

            # Skip the first token (the command itself) if it has no path separators
            # Skip empty tokens, flags, operators, URLs, pure numbers
            if ShellExecutor._NON_PATH_PATTERNS.match(stripped):
                resolved_parts.append(token)
                continue

            # Check if this looks like a path candidate
            is_path_candidate = False

            if stripped.startswith('./') or stripped.startswith('.\\'):
                is_path_candidate = True
            elif stripped.startswith('../') or stripped.startswith('..\\'):
                is_path_candidate = True
            elif os.sep in stripped or '/' in stripped:
                # Contains path separators → likely a path
                is_path_candidate = True
            elif stripped.startswith('~'):
                is_path_candidate = True

            if is_path_candidate:
                # Already absolute? Leave it.
                if os.path.isabs(stripped):
                    resolved_parts.append(token)
                    continue

                # Expand ~ and resolve relative to cwd
                expanded = os.path.expanduser(stripped)
                absolute = os.path.normpath(os.path.join(cwd, expanded))
                resolved_parts.append(f'"{absolute}"')
                changed = True
                logger.debug(f"[SHELL] Path resolved: '{stripped}' -> '{absolute}'")
            else:
                resolved_parts.append(token)

        if changed:
            resolved_cmd = ' '.join(resolved_parts)
            logger.info(f"[SHELL] Paths resolved: {command}  ->  {resolved_cmd}")
            return resolved_cmd

        return command

    @staticmethod
    async def execute(command: str, timeout: int = 30, bypass_security: bool = False) -> Dict[str, Any]:
        """
        Execute a shell command with security validation and output capture.
        Relative paths in the command are automatically resolved to absolute paths.
        """
        # 1. Security Validation (Skip if already approved)
        if not bypass_security:
            from utils.security import SecurityShield
            validation = SecurityShield.validate_cli_command(command)
            
            if validation["status"] == "blocked":
                logger.warning(f"[SHELL] BLOCKED: {command} - Reason: {validation.get('message')}")
                return {
                    "success": False,
                    "status": "error",
                    "message": f"Security Block: {validation.get('message')}"
                }
                
            if validation["status"] == "unsafe":
                logger.info(f"[SHELL] PENDING APPROVAL: {command}")
                return {
                    "success": False, # Explicitly false so collectors know it's not done
                    "status": "pending",
                    "message": "APPROVAL_REQUIRED",
                    "details": validation.get("message", "High-risk command detected."),
                    "command": command
                }

        # 2. Resolve relative paths to absolute paths
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        command = ShellExecutor._resolve_paths_in_command(command, project_root)

        # 3. Execution
        logger.info(f"[SHELL] Executing: {command} (CWD: {project_root})")
        
        try:
            # Create subprocess with explicit CWD to avoid path drift
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=project_root
            )

            # Wait for completion with timeout
            try:
                stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
                exit_code = process.returncode
                
                # Decode output
                out_str = stdout.decode().strip() if stdout else ""
                err_str = stderr.decode().strip() if stderr else ""
                
                if exit_code == 0:
                    return {
                        "success": True,
                        "status": "success",
                        "stdout": out_str,
                        "stderr": err_str,
                        "exit_code": exit_code
                    }
                else:
                    logger.warning(f"[SHELL] Failed (Code {exit_code}): {command}")
                    return {
                        "success": False,
                        "status": "error",
                        "stdout": out_str,
                        "stderr": err_str,
                        "exit_code": exit_code
                    }

            except asyncio.TimeoutError:
                process.kill()
                logger.error(f"[SHELL] Timeout ({timeout}s) exceeded: {command}")
                return {
                    "success": False,
                    "status": "error",
                    "error": "TIMEOUT",
                    "message": f"Command timed out after {timeout} seconds."
                }

        except Exception as e:
            logger.error(f"[SHELL] Execution error: {e}")
            return {
                "success": False,
                "status": "error",
                "error": "EXECUTION_ERROR",
                "message": str(e)
            }