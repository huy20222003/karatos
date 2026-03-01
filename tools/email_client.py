"""
Email Client Tool - Powered by Resend
Sends emails via Resend HTTP API. Supports HTML, professional templating, and attachments.
"""
import httpx
import base64
import os
from typing import Any, Dict, List, Optional
from utils.logger import get_logger
from config.settings import settings

logger = get_logger()

TOOL_META = {
    "name": "email_client",
    "aliases": ["email", "send_email", "mail"],
    "class_name": "EmailClient",
    "description": "Professional Communications: Send/read emails and manage IMAP/SMTP accounts.",
    "author": "Karatos Core",
    "version": "1.0.0",
    "enabled": True,
    "actions": [
        {
            "name": "send_email",
            "description": "Send an email via Resend with optional attachments.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "to": {"type": "string", "description": "Recipient email address."},
                    "subject": {"type": "string", "description": "Email subject."},
                    "body": {"type": "string", "description": "Email body content."},
                    "html": {"type": "boolean", "description": "If true, body is treated as HTML."},
                    "attachments": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of absolute file paths to attach."
                    }
                },
                "required": ["to", "subject", "body"]
            }
        }
    ]
}


class EmailClient:
    """Email operations via Resend API."""

    @classmethod
    async def execute(cls, action: str = "send_email", **params) -> Dict[str, Any]:
        """Route to appropriate email action."""
        if action in ["send_email", "send"]:
            return await cls.send_email(**params)
        
        # Default: try to send
        return await cls.send_email(**params)

    @classmethod
    def _wrap_in_template(cls, content: str, subject: str) -> str:
        """Wrap plain content in a premium HTML template."""
        return f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{subject}</title>
    <style>
        body {{
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background-color: #f8fafc;
            margin: 0;
            padding: 0;
            -webkit-font-smoothing: antialiased;
        }}
        .container {{
            max-width: 600px;
            margin: 40px auto;
            background: #ffffff;
            border-radius: 16px;
            overflow: hidden;
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06);
            border: 1px solid #e2e8f0;
        }}
        .header {{
            background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%);
            padding: 32px 40px;
            text-align: center;
        }}
        .header h1 {{
            color: #ffffff;
            margin: 0;
            font-size: 24px;
            font-weight: 700;
            letter-spacing: -0.025em;
        }}
        .content {{
            padding: 40px;
            color: #334155;
            line-height: 1.6;
            font-size: 16px;
        }}
        .content h2 {{
            color: #0f172a;
            margin-top: 0;
            font-size: 20px;
        }}
        .footer {{
            background-color: #f1f5f9;
            padding: 24px 40px;
            text-align: center;
            border-top: 1px solid #e2e8f0;
        }}
        .footer p {{
            margin: 0;
            font-size: 13px;
            color: #64748b;
        }}
        .button {{
            display: inline-block;
            padding: 12px 24px;
            background-color: #3b82f6;
            color: #ffffff;
            text-decoration: none;
            border-radius: 8px;
            font-weight: 600;
            margin-top: 24px;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>Karatos AI</h1>
        </div>
        <div class="content">
            {content}
        </div>
        <div class="footer">
            <p>© 2026 Karatos Intelligent Systems. All rights reserved.</p>
            <p style="margin-top: 8px;">Đây là email tự động, vui lòng không trả lời.</p>
        </div>
    </div>
</body>
</html>
"""

    @classmethod
    async def send_email(cls, to: str = "", subject: str = "", body: str = "",
                         html: bool = False, use_template: bool = True, 
                         attachments: List[str] = None, **kwargs) -> Dict[str, Any]:
        """Send an email via Resend API with attachments."""
        if not to or not subject or not body:
            return {"status": "error", "message": "Missing required parameters: 'to', 'subject', 'body'."}

        try:
            api_key = settings.resend_api_key
            from_email = settings.resend_from_email

            if not api_key:
                return {
                    "status": "error",
                    "message": "Resend API Key not configured. Set RESEND_API_KEY in .env"
                }

            url = "https://api.resend.com/emails"
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }
            
            # Tự động áp dụng template nếu được yêu cầu
            if use_template and not body.strip().startswith("<!DOCTYPE html>"):
                final_body = cls._wrap_in_template(body, subject)
                html = True # Luôn là HTML nếu dùng template
            else:
                final_body = body

            payload = {
                "from": from_email,
                "to": to,
                "subject": subject,
            }
            
            if html:
                payload["html"] = final_body
            else:
                payload["text"] = final_body

            # Xử lý file đính kèm
            if attachments:
                resend_attachments = []
                for file_path in attachments:
                    if not os.path.exists(file_path):
                        logger.warning(f"[EMAIL] Attachment not found: {file_path}")
                        continue
                    
                    try:
                        with open(file_path, "rb") as f:
                            file_content = f.read()
                            encoded = base64.b64encode(file_content).decode("utf-8")
                            resend_attachments.append({
                                "filename": os.path.basename(file_path),
                                "content": encoded
                            })
                    except Exception as fe:
                        logger.error(f"[EMAIL] Failed to read attachment {file_path}: {fe}")
                
                if resend_attachments:
                    payload["attachments"] = resend_attachments

            async with httpx.AsyncClient() as client:
                resp = await client.post(url, json=payload, headers=headers, timeout=30.0)
                data = resp.json()
                
                if resp.status_code in [200, 201]:
                    logger.info(f"[EMAIL] Sent email to {to} via Resend (Styled): {subject}")
                    return {
                        "status": "success", 
                        "data": {
                            "id": data.get("id"),
                            "to": to, 
                            "subject": subject
                        }
                    }
                else:
                    error_msg = data.get("message", "Unknown Resend error")
                    logger.error(f"[EMAIL] Resend error: {error_msg}")
                    return {"status": "error", "message": f"Resend API Error: {error_msg}"}

        except Exception as e:
            logger.error(f"[EMAIL] Send failed: {e}")
            return {"status": "error", "message": f"Failed to send email: {str(e)}"}
