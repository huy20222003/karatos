import os
import math
from config.settings import settings
from utils.logger import get_logger

logger = get_logger()

class HardwareEngine:
    """
    Brain Hardware Engine
    Detects system capabilities and provides optimal configuration for AI performance.
    """
    
    @staticmethod
    def get_optimal_threads(max_utility: float = None) -> int:
        """
        Calculate the optimal number of threads based on CPU cores or settings.
        """
        if max_utility is None:
            # Administrator has switched to using model_threads from settings directly
            return settings.model_threads

        try:
            logical_cores = os.cpu_count() or 4
            optimal = max(1, math.floor(logical_cores * max_utility))
            logger.info(f"[HARDWARE] Detected {logical_cores} cores. Calibrating for {optimal} threads ({max_utility*100:.0f}% utility).")
            return optimal
        except Exception as e:
            logger.warning(f"[HARDWARE] Failed to detect CPU: {e}. Falling back to default.")
            return settings.model_threads

    @staticmethod
    def get_optimal_context_size() -> int:
        """
        Calculate context size based on estimated system capabilities.
        Future versions will use psutil for RAM check.
        """
        # Default high-performance context
        return settings.model_context_size # Calibrated for administrator's local hardware (fast mode)

    @staticmethod
    def get_query_batch_size() -> int:
        """
        Calculate optimal database query batch size (row limit) 
        based on detected hardware performance.
        """
        try:
            logical_cores = os.cpu_count() or 4
            # Heuristic: 30 rows per core, capped at 200
            batch_size = min(200, logical_cores * 30)
            return max(50, batch_size) # At least 50
        except:
            return 100 # Safe default
            
    @staticmethod
    def get_calibration_report() -> dict:
        """Detailed hardware report for Niva's logs."""
        return {
            "cores": os.cpu_count(),
            "platform": HardwareEngine.get_platform(),
            "target_utility": "manual (settings.model_threads)",
            "recommended_threads": HardwareEngine.get_optimal_threads(),
            "optimized_context": HardwareEngine.get_optimal_context_size(),
            "query_batch_size": HardwareEngine.get_query_batch_size()
        }

    @staticmethod
    def get_platform() -> str:
        """Detect the host operating system."""
        import platform
        return platform.system()
