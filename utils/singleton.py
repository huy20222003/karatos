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
                                proc.kill() 
                                try:
                                    proc.wait(timeout=5)
                                except:
                                    pass
                        except (ImportError, Exception):
                            if sys.platform == 'win32':
                                subprocess.run(['taskkill', '/F', '/PID', str(old_pid)], capture_output=True)
                            else:
                                try: os.kill(old_pid, 9)
                                except: pass
                        # Critical: wait for OS to flush file handles
                        time.sleep(2)
        except Exception as e:
            logger.debug(f"[SINGLETON] Kill old instance failed: {e}")

    # 2. Acquire lock with retries
    retry_count = 5
    for attempt in range(retry_count):
        try:
            if sys.platform == 'win32':
                import msvcrt
                try:
                    # Open with O_CREAT | O_RDWR
                    _lock_fd = os.open(lockfile, os.O_CREAT | os.O_RDWR)
                    msvcrt.locking(_lock_fd, msvcrt.LK_NBLCK, 1)
                except (OSError, IOError, PermissionError):
                    if _lock_fd is not None:
                        try: os.close(_lock_fd)
                        except: pass
                    _lock_fd = None
                    if attempt < retry_count - 1:
                        logger.info(f"[SINGLETON] Lock busy, retrying... ({attempt+1}/{retry_count})")
                        time.sleep(2)
                        continue
                    return False
            else:
                import fcntl
                try:
                    _lock_fd = os.open(lockfile, os.O_CREAT | os.O_RDWR)
                    fcntl.flock(_lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except (OSError, IOError):
                    if _lock_fd is not None:
                        os.close(_lock_fd)
                    _lock_fd = None
                    if attempt < retry_count - 1:
                        time.sleep(1)
                        continue
                    return False
            
            # 3. Success: Write PID
            try:
                with open(pidfile, 'w') as f:
                    f.write(str(os.getpid()))
            except:
                pass # Non-critical if PID file write fails
            return True
            
        except Exception as e:
            logger.error(f"[SINGLETON] Lock acquisition error: {e}")
            if attempt < retry_count - 1:
                time.sleep(1)
                continue
            return True # Fail-safe
            
    return False
