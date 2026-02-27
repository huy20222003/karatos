"""
Process Monitor Tool — System Process & Service Management.
Monitor running processes, check resource usage, manage services.
Brain decides what to monitor; this tool provides the execution.
"""
import asyncio
import platform
import json
from typing import Any, Dict, List
from utils.logger import get_logger

logger = get_logger()

# Tool metadata for ToolRegistry auto-discovery
TOOL_META = {
    "name": "process_monitor",
    "aliases": ["ps", "processes"],
    "class_name": "ProcessMonitor",
    "description": "Process Monitor: Inspects running processes, checks system resource usage (CPU, RAM, disk), and manages service status. Use this ONLY for technical system metrics, NOT for current time or date.",
    "actions": [
        {
            "name": "get_system_stats",
            "description": "Get comprehensive system technical information: OS, CPU, RAM, disk usage, uptime. Does NOT return current clock time or date.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        },
        {
            "name": "list_processes",
            "description": "List running processes with CPU/memory usage. Optionally filter by name.",
            "parameters": {
                "type": "object",
                "properties": {
                    "filter_name": {"type": "string", "description": "Optional process name filter (case-insensitive)."},
                    "sort_by": {"type": "string", "description": "Sort by: 'cpu', 'memory', 'name', 'pid' (default: memory)."},
                    "top_n": {"type": "integer", "description": "Number of top processes to return (default: 20)."}
                },
                "required": []
            }
        },
        {
            "name": "check_port",
            "description": "Check if a specific port is in use and which process holds it.",
            "parameters": {
                "type": "object",
                "properties": {
                    "port": {"type": "integer", "description": "Port number to check."}
                },
                "required": ["port"]
            }
        },
        {
            "name": "network_connections",
            "description": "List active network connections with process info.",
            "parameters": {
                "type": "object",
                "properties": {
                    "filter_status": {"type": "string", "description": "Filter by status: ESTABLISHED, LISTEN, etc."}
                },
                "required": []
            }
        }
    ]
}


class ProcessMonitor:
    """Cross-platform process and system monitoring."""

    @classmethod
    async def execute(cls, _dispatched_action: str = "", action: str = "", **kwargs) -> Dict[str, Any]:
        """Unified entry point. Routes to sub-method based on dispatched action."""
        route = _dispatched_action or action or "get_system_stats"
        action_map = {
            "get_system_stats": cls.get_system_stats,
            "list_processes": cls.list_processes,
            "check_port": cls.check_port,
            "network_connections": cls.network_connections,
            "process_monitor": cls.get_system_stats,
            "ps": cls.list_processes,
            "processes": cls.list_processes,
        }
        handler = action_map.get(route, cls.get_system_stats)
        return await handler(**kwargs)

    @classmethod
    async def get_system_stats(cls) -> Dict[str, Any]:
        """Get comprehensive system information."""
        try:
            import psutil
        except ImportError:
            import subprocess, sys
            subprocess.check_call([sys.executable, "-m", "pip", "install", "psutil", "-q"])
            import psutil

        try:
            cpu_count = psutil.cpu_count()
            cpu_percent = psutil.cpu_percent(interval=1)
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage('/')
            
            # Boot time
            import datetime
            boot_time = datetime.datetime.fromtimestamp(psutil.boot_time())
            uptime = datetime.datetime.now() - boot_time

            # Network interfaces
            net_if = psutil.net_if_addrs()
            interfaces = {}
            for name, addrs in net_if.items():
                for addr in addrs:
                    if addr.family.name == 'AF_INET':
                        interfaces[name] = addr.address

            return {
                "status": "success",
                "system": {
                    "os": platform.system(),
                    "os_version": platform.version(),
                    "architecture": platform.machine(),
                    "hostname": platform.node(),
                    "python_version": platform.python_version(),
                },
                "cpu": {
                    "count": cpu_count,
                    "usage_percent": cpu_percent,
                    "freq_mhz": getattr(psutil.cpu_freq(), 'current', None),
                },
                "memory": {
                    "total_gb": round(memory.total / (1024**3), 2),
                    "used_gb": round(memory.used / (1024**3), 2),
                    "available_gb": round(memory.available / (1024**3), 2),
                    "usage_percent": memory.percent,
                },
                "disk": {
                    "total_gb": round(disk.total / (1024**3), 2),
                    "used_gb": round(disk.used / (1024**3), 2),
                    "free_gb": round(disk.free / (1024**3), 2),
                    "usage_percent": round(disk.percent, 1),
                },
                "uptime": str(uptime).split('.')[0],
                "network_interfaces": interfaces,
            }
        except Exception as e:
            logger.error(f"[PROCESS_MONITOR] System info failed: {e}")
            return {"status": "error", "message": str(e)}

    @classmethod
    async def list_processes(cls, filter_name: str = None, 
                              sort_by: str = "memory",
                              top_n: int = 20) -> Dict[str, Any]:
        """List running processes with resource usage."""
        try:
            import psutil
        except ImportError:
            import subprocess, sys
            subprocess.check_call([sys.executable, "-m", "pip", "install", "psutil", "-q"])
            import psutil

        try:
            processes = []
            for proc in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent', 
                                              'memory_info', 'status', 'create_time']):
                try:
                    info = proc.info
                    if filter_name and filter_name.lower() not in info['name'].lower():
                        continue
                    
                    processes.append({
                        "pid": info['pid'],
                        "name": info['name'],
                        "cpu_percent": info['cpu_percent'] or 0,
                        "memory_percent": round(info['memory_percent'] or 0, 2),
                        "memory_mb": round(info['memory_info'].rss / (1024**2), 1) if info['memory_info'] else 0,
                        "status": info['status'],
                    })
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue

            # Sort
            sort_map = {
                "cpu": lambda x: x["cpu_percent"],
                "memory": lambda x: x["memory_percent"],
                "name": lambda x: x["name"].lower(),
                "pid": lambda x: x["pid"],
            }
            sort_fn = sort_map.get(sort_by, sort_map["memory"])
            processes.sort(key=sort_fn, reverse=(sort_by != "name"))

            return {
                "status": "success",
                "total_processes": len(processes),
                "showing": min(top_n, len(processes)),
                "processes": processes[:top_n],
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}

    @classmethod
    async def check_port(cls, port: int) -> Dict[str, Any]:
        """Check if a port is in use."""
        try:
            import psutil
        except ImportError:
            import subprocess, sys
            subprocess.check_call([sys.executable, "-m", "pip", "install", "psutil", "-q"])
            import psutil

        try:
            connections = psutil.net_connections()
            listeners = []
            for conn in connections:
                if conn.laddr and conn.laddr.port == port:
                    proc_name = "Unknown"
                    try:
                        if conn.pid:
                            proc_name = psutil.Process(conn.pid).name()
                    except:
                        pass
                    listeners.append({
                        "pid": conn.pid,
                        "process": proc_name,
                        "status": conn.status,
                        "local_address": f"{conn.laddr.ip}:{conn.laddr.port}",
                    })

            if listeners:
                return {"status": "success", "port": port, "in_use": True, "listeners": listeners}
            else:
                return {"status": "success", "port": port, "in_use": False, "message": f"Port {port} is available."}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    @classmethod
    async def network_connections(cls, filter_status: str = None) -> Dict[str, Any]:
        """List active network connections."""
        try:
            import psutil
        except ImportError:
            import subprocess, sys
            subprocess.check_call([sys.executable, "-m", "pip", "install", "psutil", "-q"])
            import psutil

        try:
            connections = psutil.net_connections()
            results = []
            for conn in connections:
                if filter_status and conn.status != filter_status.upper():
                    continue
                
                proc_name = "Unknown"
                try:
                    if conn.pid:
                        proc_name = psutil.Process(conn.pid).name()
                except:
                    pass
                
                entry = {
                    "pid": conn.pid,
                    "process": proc_name,
                    "status": conn.status,
                    "local": f"{conn.laddr.ip}:{conn.laddr.port}" if conn.laddr else None,
                    "remote": f"{conn.raddr.ip}:{conn.raddr.port}" if conn.raddr else None,
                }
                results.append(entry)

            # Sort: ESTABLISHED first, then LISTEN
            results.sort(key=lambda x: (x["status"] != "ESTABLISHED", x["status"] != "LISTEN"))

            return {
                "status": "success",
                "total": len(results),
                "connections": results[:50],
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}
