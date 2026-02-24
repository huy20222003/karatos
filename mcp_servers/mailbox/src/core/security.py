import re
from fastapi import HTTPException, Header
from typing import Optional
from ..config import settings

class SecurityShield:
    """
    Security layer for the Mailbox MCP server.
    Handles token authentication and content sanitization.
    """
    
    # Payload limits
    MAX_CONTENT_LENGTH = 50000  # 50k chars
    
    @staticmethod
    async def verify_token(x_mailbox_token: Optional[str] = Header(None)):
        """Dependency for FastAPI to verify the auth token."""
        if not settings.mailbox_auth_token:
            # If no token configured on server, allow (dev mode)
            return True
            
        if x_mailbox_token != settings.mailbox_auth_token:
            raise HTTPException(
                status_code=401, 
                detail="Unauthorized: Invalid or missing X-Mailbox-Token header."
            )
        return True

    @classmethod
    def sanitize_content(cls, content: str) -> str:
        """
        Sanitizes incoming message content to prevent injection and bloat.
        """
        if not content:
            return ""
            
        # 1. Length limiting
        if len(content) > cls.MAX_CONTENT_LENGTH:
            content = content[:cls.MAX_CONTENT_LENGTH] + "... [TRUNCATED BY SECURITY SHIELD]"
            
        # 2. XSS/Script Injection Prevention (Basic)
        # Remove common HTML/Script tags
        content = re.sub(r'<script.*?>.*?</script>', '[SCRIPT_REMOVED]', content, flags=re.IGNORECASE | re.DOTALL)
        content = re.sub(r'<.*?>', '', content)  # Strip all other HTML tags
        
        # 3. ANSI/Control character removal
        content = re.sub(r'\x1b\[[0-9;]*[mGKF]', '', content)
        
        return content.strip()
