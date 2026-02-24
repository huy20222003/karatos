import os
import sys
import tempfile
import hashlib
import time
import subprocess
from utils.logger import get_logger

logger = get_logger()

# Keep a reference to the file descriptor so it's not garbage collected
_lock_fd = None

def acquire_or_kill_single_instance(instance_name: str) -> bool:
    """
    Acquire a cross-platform single-instance file lock.
    If another instance is running, kill it and take over.
    Returns True if the lock was acquired.
    Returns False if it failed to acquire the lock (e.g., race condition).
    """
    global _lock_fd
    
    hash_name = hashlib.md5(instance_name.encode('utf-8')).hexdigest()
    lockfile = os.path.join(tempfile.gettempdir(), f"brain_{hash_name}.lock")
    pidfile = os.path.join(tempfile.gettempdir(), f"brain_{hash_name}.pid")
    
    # 1. Kill existing instance if running
    if os.path.exists(pidfile):
        try:
            with open(pidfile, 'r') as f:
                old_pid_str = f.read().strip()
                if old_pid_str.isdigit():
                    old_pid = int(old_pid_str)
                    if old_pid != os.getpid():
                        logger.warning(f"[SINGLETON] Found previous instance (PID: {old_pid}). Terminating it to take over...")
                        try:
                            import psutil
                            if psutil.pid_exists(old_pid):
                                proc = psutil.Process(old_pid)
                                # Extra safety to not kill unrelated processes
                                if "python" in proc.name().lower():
                                    proc.terminate()
                                    try:
                                        proc.wait(timeout=3)
                                    except psutil.TimeoutExpired:
                                        proc.kill()
                        except ImportError:
                            # Fallback if psutil is not available
                            if sys.platform == 'win32':
                                subprocess.run(['taskkill', '/F', '/PID', str(old_pid)], capture_output=True)
                            else:
                                import signal
                                try:
                                    os.kill(old_pid, signal.SIGKILL)
                                except OSError:
                                    pass
        except Exception as e:
            logger.debug(f"[SINGLETON] Failed to read or kill old instance: {e}")

    # Give OS a moment to release file handles from the killed process
    time.sleep(1)

    # 2. Acquire lock
    try:
        if sys.platform == 'win32':
            import msvcrt
            _lock_fd = os.open(lockfile, os.O_CREAT | os.O_RDWR)
            try:
                msvcrt.locking(_lock_fd, msvcrt.LK_NBLCK, 1)
            except OSError:
                # Still locked by something else
                os.close(_lock_fd)
                _lock_fd = None
                return False
        else:
            import fcntl
            _lock_fd = os.open(lockfile, os.O_CREAT | os.O_RDWR)
            try:
                fcntl.flock(_lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                os.close(_lock_fd)
                _lock_fd = None
                return False
                
        # 3. Write our current PID for future replacement
        with open(pidfile, 'w') as f:
            f.write(str(os.getpid()))
            
        return True
    except Exception as e:
        logger.error(f"[SINGLETON] Error acquiring lock: {e}")
        return True # Fail-safe: allow running if the locking mechanism crashes
