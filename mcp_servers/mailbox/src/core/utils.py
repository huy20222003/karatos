import psutil
import os
import signal

def kill_process_on_port(port: int):
    """Checks for processes running on the specified port and terminates them."""
    print(f"[SYSTEM] Checking for processes on port {port}...")
    for proc in psutil.process_iter(['pid', 'name']):
        try:
            connections = proc.connections(kind='inet')
            for conn in connections:
                if conn.laddr.port == port:
                    print(f"[SYSTEM] Found process {proc.info['name']} (PID: {proc.info['pid']}) on port {port}. Terminating...")
                    
                    # Try graceful termination first
                    proc.terminate()
                    try:
                        proc.wait(timeout=3)
                    except psutil.TimeoutExpired:
                        # Force kill if still alive
                        print(f"[SYSTEM] Process {proc.info['pid']} did not terminate in time. Killing...")
                        proc.kill()
                    
                    print(f"[SYSTEM] Successfully freed port {port}.")
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass
        except Exception as e:
            print(f"[SYSTEM] Error while checking/killing process: {e}")
