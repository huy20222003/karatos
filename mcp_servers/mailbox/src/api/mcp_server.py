import json
from mcp.server.fastmcp import FastMCP
from ..core.communication import CommunicationManager

from ..config import settings

# Initialize FastMCP
mcp = FastMCP(settings.SERVER_NAME)

# Internal manager instance
comm_manager = CommunicationManager()

@mcp.tool()
def drop_message(sender: str, target: str, chat_id: str, content: str) -> str:
    """Drop a message for one or multiple bots into the networked mailbox.
    
    Args:
        sender: The username or name of the sender bot (e.g. @bot1 or "Nivacore").
        target: The target(s). Can be a single name/username or a comma-separated list (e.g. "Sentry, @bot2").
        chat_id: The chat ID where this was initiated.
        content: The actual message content.
    """
    successful_targets = comm_manager.drop_message(
        sender=sender,
        targets=target,
        chat_id=chat_id,
        content=content
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
