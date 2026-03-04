import os
import time
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from utils.logger import get_logger

logger = get_logger()

class ConfigDirectoryHandler(FileSystemEventHandler):
    """Handles file system events for an entire configuration directory."""
    def __init__(self, callback, extensions=(".json",)):
        self.callback = callback
        self.extensions = extensions
        self.last_triggered = 0
        self.debounce_seconds = 1.0

    def on_modified(self, event):
        if event.is_directory:
            return
        
        # Only trigger for specific extensions (e.g. .json config files)
        filename = os.path.basename(event.src_path)
        if any(filename.endswith(ext) for ext in self.extensions):
            now = time.time()
            if now - self.last_triggered > self.debounce_seconds:
                self.last_triggered = now
                logger.debug(f"[CONFIG_WATCHER] Change detected in: {filename}")
                self.callback()

def start_config_watcher(path, callback, is_directory=True):
    """
    Starts a background thread to watch for changes in a directory.
    Returns the observer instance.
    """
    if not os.path.exists(path):
        logger.warning(f"[CONFIG_WATCHER] Target {path} does not exist. Watcher not started.")
        return None

    path = os.path.abspath(path)
    if not os.path.isdir(path):
        # Fallback to directory of the file if a file path was passed
        path = os.path.dirname(path)

    logger.info(f"[CONFIG_WATCHER] Monitoring directory {path} for config changes...")

    observer = Observer()
    handler = ConfigDirectoryHandler(callback)
    observer.schedule(handler, path, recursive=False)
    observer.start()
    
    return observer
