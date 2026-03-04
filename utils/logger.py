"""
Agent Logger
Custom logging system for the autonomous agent
"""
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional
from rich.console import Console
from rich.logging import RichHandler


class AgentLogger:
    """
    Custom logger for the Brain agent.
    Supports both file and console output with rich formatting.
    """
    
    _instance: Optional["AgentLogger"] = None
    
    def __new__(cls) -> "AgentLogger":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self._initialized = True
        self.console = Console(force_terminal=True)
        self.logger = logging.getLogger("Brain")
        self._setup_logger()
    
    def _setup_logger(self):
        """Configure the logging handlers"""
        from config.settings import settings
        
        self.logger.setLevel(getattr(logging, settings.log_level.upper()))
        
        # Remove existing handlers and disable propagation
        self.logger.handlers.clear()
        self.logger.propagate = False
        
        # Console handler with rich formatting
        console_handler = RichHandler(
            console=self.console,
            show_time=True,
            show_path=False,
            rich_tracebacks=True
        )
        console_handler.setLevel(logging.DEBUG)
        console_format = logging.Formatter("%(message)s")
        console_handler.setFormatter(console_format)
        self.logger.addHandler(console_handler)
        
        # File handler
        log_dir = Path(settings.log_dir)
        log_dir.mkdir(parents=True, exist_ok=True)
        
        date_str = datetime.now().strftime("%Y-%m-%d")
        log_file = log_dir / f"agent-{date_str}.log"
        
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setLevel(logging.DEBUG)
        file_format = logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        file_handler.setFormatter(file_format)
        self.logger.addHandler(file_handler)
    
    def debug(self, message: str, **kwargs):
        """Log debug message"""
        self.logger.debug(message, **kwargs)
    
    def info(self, message: str, **kwargs):
        """Log info message"""
        self.logger.info(message, **kwargs)
    
    def warning(self, message: str, **kwargs):
        """Log warning message"""
        self.logger.warning(message, **kwargs)
    
    def error(self, message: str, **kwargs):
        """Log error message"""
        self.logger.error(message, **kwargs)
    
    def critical(self, message: str, **kwargs):
        """Log critical message"""
        self.logger.critical(message, **kwargs)
    
    def thought(self, message: str):
        """
        Log an agent thought (internal monologue).
        Uses special formatting to distinguish from regular logs.
        """
        self.logger.info(f"[THOUGHT] {message}")
    
    def observation(self, message: str):
        """Log an observation from data analysis"""
        self.logger.info(f"[OBSERVATION] {message}")
    
    def decision(self, message: str):
        """Log a decision made by the agent"""
        self.logger.info(f"[DECISION] {message}")
    
    def action(self, message: str):
        """Log an action being executed"""
        self.logger.info(f"[ACTION] {message}")
    
    def result(self, success: bool, message: str):
        """Log the result of an action"""
        if success:
            self.logger.info(f"[RESULT:SUCCESS] {message}")
        else:
            self.logger.error(f"[RESULT:FAILED] {message}")


def get_logger() -> AgentLogger:
    """Get the singleton logger instance"""
    return AgentLogger()
