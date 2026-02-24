import json
from mcp.server.fastmcp import FastMCP
from ..core.communication import CommunicationManager
from ..core.security import SecurityShield
from fastapi import Depends
from ..config import settings

# Initialize FastMCP
mcp = FastMCP(settings.SERVER_NAME)

# Internal manager instance
comm_manager = CommunicationManager()

# Access the underlying FastAPI app
app = mcp.sse_app()

# --- MIDDLEWARE (Raw ASGI for SSE compatibility) ---
# --- MIDDLEWARE (Raw ASGI for SSE compatibility) ---
class ASGIMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        
        # Only protect key MCP endpoints
        if path.startswith("/sse") or path.startswith("/messages") or path.startswith("/tools"):
            # Extract headers from scope for raw inspection (tuples of byte-strings)
            headers = dict(scope.get("headers", []))
            token = headers.get(b"x-mailbox-token", b"").decode("utf-8")
            
            try:
                await SecurityShield.verify_token(token)
            except Exception:
                # print(f"[AUTH] ❌ Blocked: {scope['method']} {path}")
                from starlette.responses import JSONResponse
                response = JSONResponse(status_code=401, content={"detail": "Unauthorized"})
                await response(scope, receive, send)
                return

        await self.app(scope, receive, send)

# Apply raw ASGI middleware manually to the sse_app
app.add_middleware(ASGIMiddleware)

@app.on_event("startup")
async def startup_event():
    print(f"[SYSTEM] Mailbox Server starting up...")

@app.on_event("shutdown")
async def shutdown_event():
    print(f"[SYSTEM] Mailbox Server shutting down gracefully...")
    comm_manager.save_all()

@mcp.tool()
def drop_message(sender: str, target: str, chat_id: str, content: str) -> str:
    """Drop a message for one or multiple bots into the networked mailbox.
    
    Args:
        sender: The username or name of the sender bot (e.g. @bot1 or "Nivacore").
        target: The target(s). Can be a single name/username or a comma-separated list (e.g. "Sentry, @bot2").
        chat_id: The chat ID where this was initiated.
        content: The actual message content.
    """
    # Sanitize content before dropping
    safe_content = SecurityShield.sanitize_content(content)
    
    successful_targets = comm_manager.drop_message(
        sender=sender,
        targets=target,
        chat_id=chat_id,
        content=safe_content
    )
    return f"Successfully dropped message for: {', '.join(successful_targets)}"

@mcp.tool()
def check_mailbox(my_username: str) -> str:
    """Check all messages targeting my_username or name. Consumes (deletes) them after reading.
    
    Args:
        my_username: The username or name of the bot checking its mailbox (e.g. @bot2 or "Sentry").
    """
    messages = comm_manager.consume_messages(my_username)
    return json.dumps(messages, ensure_ascii=False)

@mcp.tool()
def register_bot(name: str, username: str) -> str:
    """Register or update a bot's identity (Name <-> Username mapping).
    
    Args:
        name: The human-readable name (e.g. "Sentry").
        username: The @username handle (e.g. "@niva_sentry_bot").
    """
    comm_manager.register_identity(name, username)
    return f"Registered identity: {name} as {username}"

@mcp.tool()
def get_registrations() -> str:
    """Get all registered bot identities as a JSON map of Name -> @username."""
    return json.dumps(comm_manager.get_registrations(), ensure_ascii=False)
