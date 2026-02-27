"""
Notification Manager Utility
Centralizes all human-in-the-loop communication, including direct alerts and approval requests.
Language-aware: auto-detects user language to localize all UI messages.
"""
import json
import uuid
from pathlib import Path
from typing import Optional, Any
from config.settings import settings
from utils.logger import get_logger

logger = get_logger()

class NotificationManager:
    """
    Unified manager for sending notifications to the Administrator.
    Supports both direct alerts (no approval) and interactive requests (approval required).
    Delegates all human-facing text to the Brain instead of local hardcoded templates.
    """

    @staticmethod
    def _detect_language(lang_override: Optional[str] = None) -> str:
        """
        Choose language code based primarily on Brain/InputPipeline signal,
        avoiding local heuristics as much as possible.
        """
        # 0. Prefer explicit value coming from Brain / InputPipeline
        if lang_override:
            code = str(lang_override).lower()
            # Normalize "mixed" to Vietnamese to avoid hybrid outputs.
            if code == "mixed":
                code = "vi"
            if code in ("vi", "en"):
                return code

        # 1. Optional static configuration fallback
        lang = getattr(settings, "user_language", None)
        if isinstance(lang, str):
            code = lang.lower()
            if code == "mixed":
                code = "vi"
            if code in ("vi", "en"):
                return code

        # 2. Default: English if nothing else is known
        return "en"

    @staticmethod
    async def _generate_brain_body(context_msg: str, language: Optional[str] = None) -> str:
        """Ask the brain to generate a stylized, localized message body."""
        try:
            from core.brain.model import BrainModel
            from core.brain.prompts.registry import get_prompt_registry
            from config.settings import settings
            
            lang_code = NotificationManager._detect_language(language)
            lang_val = "Vietnamese" if lang_code == "vi" else "English"
            
            prompt = get_prompt_registry().get(
                "persona.generator.system_feedback",
                context_msg=context_msg,
                language=lang_val
            )
            
            model = BrainModel(mode="brief")
            response = await model.think(prompt, phase="brief")
            
            from core.brain.utils import get_llm_content, strip_thinking_tags
            return strip_thinking_tags(get_llm_content(response))
        except Exception as e:
            logger.error(f"[NOTIFICATION] Brain synthesis failed: {e}")
            return context_msg # Fallback to raw context if brain fails

    @staticmethod
    async def send_alert(title: str, body: str, severity: str = "info", channel_name: str = "telegram", language: Optional[str] = None) -> bool:
        """
        Send direct notification without approval (Direct Alerts).
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
    def _get_approval_store_path() -> Path:
        """Path to the file storing pending approval commands."""
        return Path(getattr(settings, 'base_dir', '.')) / "data" / "pending_approvals.json"

    @staticmethod
    def _save_pending_command(command: str, language: Optional[str] = None) -> str:
        """Store the command and its language, return a short ID."""
        path = NotificationManager._get_approval_store_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        
        store = {}
        if path.exists():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    store = json.load(f)
            except: pass
            
        approval_id = str(uuid.uuid4())[:8]
        # Store both command and lang so callback uses correct language
        store[approval_id] = {
            "command": command,
            "language": NotificationManager._detect_language(language)
        }
        
        with open(path, "w", encoding="utf-8") as f:
            json.dump(store, f, indent=2)
        return approval_id

    @staticmethod
    def _pop_pending_command(approval_id: str) -> tuple[Optional[str], Optional[str]]:
        """Retrieve the command and its language from storage and remove it."""
        path = NotificationManager._get_approval_store_path()
        if not path.exists():
            return None, None
            
        store = {}
        try:
            with open(path, "r", encoding="utf-8") as f:
                store = json.load(f)
        except: return None, None
        
        cmd_data = store.pop(approval_id, None)
        
        if cmd_data:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(store, f, indent=2)
                
        # Handle legacy schema (just string) vs new schema (dict)
        if isinstance(cmd_data, str):
            return cmd_data, "en" # Fallback if migrating seamlessly
        elif isinstance(cmd_data, dict):
            return cmd_data.get("command"), cmd_data.get("language")
            
        return None, None

    @staticmethod
    async def request_approval(command: str, reason: str, channel_name: str = "telegram", language: Optional[str] = None) -> bool:
        """
        Send notification requiring approval with interactive buttons.
        Language is auto-detected.
        """
        from channels.base import get_channel
        channel = get_channel(channel_name)
        
        if not channel:
            logger.error(f"[NOTIFICATION] Channel '{channel_name}' not found for approval.")
            return False

        if not isinstance(command, str):
            logger.warning(f"[NOTIFICATION] Command is not a string ({type(command)}). Converting.")
            command = str(command)
            
        approval_id = NotificationManager._save_pending_command(command, language)
        lang_code = NotificationManager._detect_language(language)
        
        if channel_name == "telegram":
            logger.info(f"[NOTIFICATION] Triggering Telegram approval for command: {command}")
            keyboard = {
                "inline_keyboard": [[
                    # Use icon-only buttons so text localization is handled by Brain messages.
                    {"text": "🚀", "callback_data": f"cli_approve:{approval_id}"},
                    {"text": "🚫", "callback_data": f"cli_deny:{approval_id}"}
                ]]
            }
            
            message_body = await NotificationManager._generate_brain_body(
                (
                    "You must ask the administrator to APPROVE or DENY the following CLI command before execution.\n"
                    f"Command: `{command}`\n"
                    f"Reason: {reason}\n"
                    "Explain clearly what this command will do and how to respond using the approval buttons."
                ),
                lang_code
            )

            return await channel.send(message_body, recipient=channel.admin_chat_id, keyboard=keyboard)
        else:
            return await channel.ask_confirmation(
                f"Approval Required: {command}\nReason: {reason}",
                channel.admin_chat_id
            )

    @staticmethod
    async def handle_approval_callback(data: str, channel: Any, sender_id: str, callback_id: Optional[str] = None) -> Optional[str]:
        """
        Process responses from approval buttons.
        All response messages are language-aware.
        """
        if data.startswith("cli_approve:") or data.startswith("cli_deny:"):
            # 0. Immediate Visual Feedback (NGO Fix)
            if callback_id and hasattr(channel, 'answer_callback_query'):
                await channel.answer_callback_query(callback_id)
                
            action = "APPROVE" if data.startswith("cli_approve:") else "DENY"
            
            try:
                approval_id = data.split(":", 1)[1]
                command, lang = NotificationManager._pop_pending_command(approval_id)
                lang_code = NotificationManager._detect_language(lang)
                
                if not command:
                    # Use Brain to explain that this approval request is no longer valid.
                    return await NotificationManager._generate_brain_body(
                        "This approval request is no longer valid because it has already been processed or has expired. "
                        "Inform the user clearly and politely that they may need to trigger the action again if still needed.",
                        lang_code
                    )
                
                if action == "DENY":
                    logger.info(f"[NOTIFICATION] Command denied by user: {command}")
                    return await NotificationManager._generate_brain_body(
                        f"The administrator has DENIED execution of the command: `{command}`. "
                        "Acknowledge this clearly and confirm that you will not run the command.",
                        lang_code
                    )
                
                # Execute the approved command
                logger.info(f"[NOTIFICATION] Command approved by user: {command}. Executing with bypass.")
                await channel.send(
                    await NotificationManager._generate_brain_body(
                        f"The administrator has APPROVED the command: `{command}`. "
                        "Tell the user that you are now starting execution and then wait for the execution result.",
                        lang_code
                    ),
                    recipient=sender_id
                )
                
                from tools.shell_executor import ShellExecutor
                result = await ShellExecutor.execute(command, bypass_security=True)
                
                status_msg = "SUCCESS" if result.get("success") else f"FAILED (exit code {result.get('exit_code', 'unknown')})"
                output_snip = f"\nOutput: {result.get('stdout')[:500]}" if result.get("stdout") else ""
                error_snip = f"\nError: {result.get('stderr')[:500]}" if result.get("stderr") else ""
                
                return await NotificationManager._generate_brain_body(
                    f"Execution of CLI command `{command}` finished with status: {status_msg}.{output_snip}{error_snip}",
                    lang_code
                )

            except Exception as e:
                logger.error(f"[NOTIFICATION] Error processing approval callback: {e}")
                return await NotificationManager._generate_brain_body(
                    f"There was an error while processing the approval callback for a CLI command: {e}. "
                    "Explain this to the user in simple terms and suggest that they retry or contact an administrator.",
                    lang_code
                )

        return None
