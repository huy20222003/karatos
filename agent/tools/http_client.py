"""
HTTP Client Tool — Generic REST API Client.
Supports GET, POST, PUT, DELETE, PATCH with headers, auth, and JSON/form payloads.
The Brain decides which endpoints to call and how to structure requests.
"""
import asyncio
import json
from typing import Any, Dict, Optional
from utils.logger import get_logger

logger = get_logger()

# Tool metadata for ToolRegistry auto-discovery
TOOL_META = {
    "name": "http_client",
    "aliases": ["http", "api_request", "rest"],
    "class_name": "HTTPClient",
    "description": "HTTP Client: Makes REST API requests (GET, POST, PUT, DELETE, PATCH) to external services. Supports JSON payloads, custom headers, authentication, and timeout controls.",
    "actions": [
        {
            "name": "http_request",
            "description": "Make an HTTP request to a URL. Supports all standard methods and authentication.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "The full URL to request."},
                    "method": {"type": "string", "description": "HTTP method: GET, POST, PUT, DELETE, PATCH (default: GET)."},
                    "headers": {"type": "object", "description": "Optional HTTP headers as key-value pairs."},
                    "body": {"type": "object", "description": "Optional request body (JSON)."},
                    "timeout": {"type": "integer", "description": "Request timeout in seconds (default: 30)."},
                    "auth_token": {"type": "string", "description": "Optional Bearer token for Authorization header."}
                },
                "required": ["url"]
            }
        }
    ]
}


class HTTPClient:
    """
    Async HTTP client for making REST API calls.
    Uses httpx for async support with connection pooling.
    """
    
    # Security: Block internal/private network requests
    BLOCKED_HOSTS = {"localhost", "127.0.0.1", "0.0.0.0", "::1"}
    BLOCKED_PREFIXES = ("10.", "172.16.", "172.17.", "172.18.", "172.19.",
                        "172.20.", "172.21.", "172.22.", "172.23.", "172.24.",
                        "172.25.", "172.26.", "172.27.", "172.28.", "172.29.",
                        "172.30.", "172.31.", "192.168.")

    @classmethod
    def _validate_url(cls, url: str) -> bool:
        """Check if URL is safe to request (not internal network)."""
        from urllib.parse import urlparse
        parsed = urlparse(url)
        host = parsed.hostname or ""
        
        if host in cls.BLOCKED_HOSTS:
            return False
        if any(host.startswith(p) for p in cls.BLOCKED_PREFIXES):
            return False
        if not parsed.scheme in ("http", "https"):
            return False
        return True

    @classmethod
    async def execute(cls, url: str, method: str = "GET", headers: dict = None,
                      body: dict = None, timeout: int = 30, 
                      auth_token: str = None) -> Dict[str, Any]:
        """Execute an HTTP request."""
        try:
            import httpx
        except ImportError:
            import subprocess, sys
            subprocess.check_call([sys.executable, "-m", "pip", "install", "httpx", "-q"])
            import httpx

        method = method.upper()
        if method not in ("GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"):
            return {"status": "error", "message": f"Unsupported HTTP method: {method}"}

        if not cls._validate_url(url):
            return {"status": "error", "message": "Request blocked: internal/private network URLs are not allowed."}

        req_headers = headers or {}
        if auth_token:
            req_headers["Authorization"] = f"Bearer {auth_token}"
        
        if "User-Agent" not in req_headers:
            req_headers["User-Agent"] = "Karatos-Agent/1.0"

        try:
            async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
                kwargs = {"headers": req_headers}
                
                if method in ("POST", "PUT", "PATCH") and body:
                    if isinstance(body, dict):
                        kwargs["json"] = body
                    else:
                        kwargs["content"] = str(body)

                response = await client.request(method, url, **kwargs)
                
                # Parse response
                content_type = response.headers.get("content-type", "")
                
                if "application/json" in content_type:
                    try:
                        resp_body = response.json()
                    except:
                        resp_body = response.text[:5000]
                else:
                    resp_body = response.text[:5000]

                return {
                    "status": "success",
                    "data": {
                        "http_status": response.status_code,
                        "headers": dict(response.headers),
                        "body": resp_body,
                        "url": str(response.url),
                        "elapsed_ms": int(response.elapsed.total_seconds() * 1000)
                    }
                }

        except httpx.TimeoutException:
            return {"status": "error", "message": f"Request timed out after {timeout}s", "url": url}
        except httpx.ConnectError as e:
            return {"status": "error", "message": f"Connection failed: {str(e)}", "url": url}
        except Exception as e:
            logger.error(f"[HTTP_CLIENT] Request failed: {e}")
            return {"status": "error", "message": str(e), "url": url}
