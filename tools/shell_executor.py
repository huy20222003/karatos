import asyncio
import subprocess
from typing import Dict, Any, Optional
from utils.logger import get_logger
from utils.security import SecurityShield

logger = get_logger()

# Tool metadata for ToolRegistry auto-discovery
TOOL_META = {
    "name": "shell_executor",
    "aliases": ["execute", "bash", "shell", "terminal"],
    "class_name": "ShellExecutor",
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

    @staticmethod
    async def execute(command: str, timeout: int = 30, bypass_security: bool = False) -> Dict[str, Any]:
        """
        Execute a shell command with security validation and output capture.
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

        # 2. Execution
        logger.info(f"[SHELL] Executing: {command}")
        
        try:
            # Create subprocess
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
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