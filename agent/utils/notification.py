"""
Notification Manager Utility
Centralizes all human-in-the-loop communication, including direct alerts and approval requests.
"""
import base64
from typing import Optional, Any
from config.settings import settings
from utils.logger import get_logger

logger = get_logger()

class NotificationManager:
    """
    Unified manager for sending notifications to the Administrator.
    Supports both direct alerts (no approval) and interactive requests (approval required).
    """

    @staticmethod
    async def send_alert(title: str, body: str, severity: str = "info", channel_name: str = "telegram") -> bool:
        """
        Gửi thông báo không cần duyệt (Direct Alerts).
        
        Args:
            title: Tiêu đề thông báo (e.g. 'CRITIC ALERT')
            body: Nội dung chi tiết
            severity: Mức độ (info, warning, error, critical)
            channel_name: Kênh thông báo (mặc định telegram)
        """
        from channels.base import get_channel
        channel = get_channel(channel_name)
        
        if not channel:
            logger.error(f"[NOTIFICATION] Channel '{channel_name}' not found for alert.")
            return False
            
        logger.info(f"[NOTIFICATION] Sending direct alert [{severity}]: {title}")
        return await channel.send_notification(
            title=title,
            body=body,
            severity=severity
        )

    @staticmethod
    async def request_approval(command: str, reason: str, channel_name: str = "telegram") -> bool:
        """
        Gửi thông báo cần duyệt (Interactive Approvals).
        
        Args:
            command: Lệnh CLI cần chạy
            reason: Lý do cần phê duyệt
            channel_name: Kênh gửi yêu cầu
        """
        from channels.base import get_channel
        channel = get_channel(channel_name)
        
        if not channel:
            logger.error(f"[NOTIFICATION] Channel '{channel_name}' not found for approval.")
            return False

        logger.info(f"[NOTIFICATION] Requesting approval for: {command}")
        
        # Encode command to safely pass through callback data
        encoded_cmd = base64.b64encode(command.encode('utf-8')).decode('utf-8')
        
        # Preparing UI components for Telegram
        if channel_name == "telegram":
            keyboard = {
                "inline_keyboard": [[
                    {"text": "🚀 Đồng ý chạy", "callback_data": f"cli_approve:{encoded_cmd}"},
                    {"text": "🚫 Từ chối", "callback_data": f"cli_deny:{encoded_cmd}"}
                ]]
            }
            
            message = (
                f"⚖️ *Niva Pro CLI: Yêu cầu phê duyệt lệnh*\n\n"
                f"• *Lệnh:* `{command}`\n"
                f"• *Lý do:* _{reason}_\n\n"
                f"{settings.user_pronoun} có cho phép {settings.bot_pronoun} thực thi lệnh này không ạ? "
                f"{settings.bot_pronoun.capitalize()} cam kết tuân thủ mọi quy tắc bảo mật của {settings.user_pronoun}! 🛡️"
            )
            
            return await channel.send(message, recipient=channel.admin_chat_id, keyboard=keyboard)
        
        # Fallback for other channels
        return await channel.ask_confirmation(f"Approval Required: {command}\nReason: {reason}", channel.admin_chat_id)

    @staticmethod
    async def handle_approval_callback(data: str, channel: Any, sender_id: str) -> Optional[str]:
        """
        Xử lý phản hồi từ các nút bấm phê duyệt.
        
        Args:
            data: Callback data từ channel
            channel: Instance của channel nhận callback
            sender_id: ID người bấm nút
        """
        if data.startswith("cli_approve:") or data.startswith("cli_deny:"):
            action = "APPROVE" if data.startswith("cli_approve:") else "DENY"
            
            try:
                encoded_cmd = data.split(":", 1)[1]
                command = base64.b64decode(encoded_cmd).decode('utf-8')
                
                if action == "DENY":
                    logger.info(f"[NOTIFICATION] Command denied by user: {command}")
                    return f"Understood! I will never run command `{command}` without {settings.user_pronoun}'s approval. Security first! 🛡️⚖️"
                
                # Execute the approved command
                logger.info(f"[NOTIFICATION] Command approved by user: {command}")
                from tools.shell_executor import ShellExecutor
                
                await channel.send(f"🚀 *Approved!* Executing: `{command}`...", recipient=sender_id)
                
                result = await ShellExecutor.execute(command)
                
                status_emoji = "✅" if result["success"] else "❌"
                feedback = (
                    f"{status_emoji} *Command Execution Result*\n"
                    f"• Command: `{command}`\n"
                    f"• Status: `{'Success' if result['success'] else 'Failed (Code ' + str(result['exit_code']) + ')'}`\n"
                )
                
                if result.get("stdout"):
                    feedback += f"\n📄 *Output:*\n```\n{result['stdout'][:800]}\n```"
                if result.get("stderr"):
                    feedback += f"\n⚠️ *Error:*\n```\n{result['stderr'][:500]}\n```"
                    
                return feedback

            except Exception as e:
                logger.error(f"[NOTIFICATION] Error processing approval callback: {e}")
                return f"❌ Error processing command approval: {e}"

        return None
