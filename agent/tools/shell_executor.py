import asyncio
import subprocess
from typing import Dict, Any, Optional
from utils.logger import get_logger

logger = get_logger()

class ShellExecutor:
    """
    Asynchronous shell command executor for Brain.
    Ensures commands are run with timeouts and output is captured securely.
    """

    @staticmethod
    async def execute(command: str, timeout: int = 30) -> Dict[str, Any]:
        """
        Execute a shell command and capture output.
        Returns: {"success": bool, "stdout": str, "stderr": str, "exit_code": int}
        """
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
                    logger.info(f"[SHELL] Success: {command}")
                    return {
                        "success": True,
                        "stdout": out_str,
                        "stderr": err_str,
                        "exit_code": exit_code
                    }
                else:
                    logger.warning(f"[SHELL] Failed (Code {exit_code}): {command}")
                    return {
                        "success": False,
                        "stdout": out_str,
                        "stderr": err_str,
                        "exit_code": exit_code
                    }

            except asyncio.TimeoutError:
                process.kill()
                logger.error(f"[SHELL] Timeout ({timeout}s) exceeded: {command}")
                return {
                    "success": False,
                    "error": "TIMEOUT",
                    "message": f"Command timed out after {timeout} seconds."
                }

        except Exception as e:
            logger.error(f"[SHELL] Execution error: {e}")
            return {
                "success": False,
                "error": "EXECUTION_ERROR",
                "message": str(e)
            }

if __name__ == "__main__":
    # Test execution
    async def test():
        executor = ShellExecutor()
        result = await executor.execute("echo 'Hello from Niva CLI'")
        print(f"Result: {result}")
        
    asyncio.run(test())
