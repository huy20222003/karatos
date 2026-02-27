"""
Settings Configuration
Centralized configuration management using Pydantic Settings
"""
import os
from pathlib import Path
from typing import Optional
from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    """Application settings loaded from environment variables"""
    
    # ===========================================
    # Database Configuration (Read-only)
    # ===========================================
    database_url: str = Field(
        default="",
        description="PostgreSQL connection string",
        alias="DATABASE_URL"
    )
    
    # ===========================================
    # LLM Provider Selection
    # ===========================================
    llm_provider: str = Field(
        default="ollama",
        description="LLM Provider to use (ollama, openai, anthropic, deepseek)",
        alias="LLM_PROVIDER"
    )

    # ===========================================
    # LLM Ollama specialized models
    # ===========================================
    ollama_embedding_model_name: str = Field(
        default="nomic-embed-text",
        description="Name of the embedding model in Ollama",
        alias="OLLAMA_EMBEDDING_MODEL_NAME"
    )
    ollama_vision_model_name: str = Field(
        default="llama3.2-vision",
        description="Name of the model in Ollama",
        alias="OLLAMA_VISION_MODEL_NAME"
    )

    # ===========================================
    # LLM Model Configuration (Ollama)
    # ===========================================
    ollama_base_url: str = Field(
        default="http://127.0.0.1:11434",
        description="Base URL for the Ollama server",
        alias="OLLAMA_BASE_URL"
    )
    ollama_model_name: str = Field(
        default="nivacore",
        description="Name of the model in Ollama",
        alias="OLLAMA_MODEL_NAME"
    )
    model_context_size: int = Field(
        default=8192,
        description="Context window size for the model",
        alias="MODEL_CONTEXT_SIZE"
    )
    model_threads: int = Field(
        default_factory=lambda: max(1, (os.cpu_count() or 4) - 1),
        description="Number of CPU threads (Auto-detected: CPU-1)",
        alias="MODEL_THREADS"
    )
    model_parallelism: int = Field(
        default=2,
        description="Number of parallel request slots (num_parallel)",
        alias="MODEL_PARALLELISM"
    )
    model_temperature: float = Field(
        default=0.3,
        description="Sampling temperature for generation",
        alias="MODEL_TEMPERATURE"
    )
    model_max_tokens: int = Field(
        default=8192,
        description="Maximum tokens to generate per response",
        alias="MODEL_MAX_TOKENS"
    )
    ollama_headers: dict = Field(
        default_factory=lambda: {
            "ngrok-skip-browser-warning": "true",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        },
        description="Custom headers for all Ollama requests",
        alias="OLLAMA_HEADERS"
    )

    # ===========================================
    # Whisper Configuration
    # ===========================================
    whisper_model_size: str = Field(
        default="small",
        description="Whisper model size (tiny, base, small, medium, large-v3)",
        alias="WHISPER_MODEL_SIZE"
    )

    # ===========================================
    # OpenAI & Compatible Providers
    # ===========================================
    openai_api_key: Optional[str] = Field(
        default=None,
        description="API Key for OpenAI or compatible provider",
        alias="OPENAI_API_KEY"
    )
    openai_api_base: Optional[str] = Field(
        default="https://api.openai.com/v1",
        description="Base URL for OpenAI or compatible API (DeepSeek, etc.)",
        alias="OPENAI_API_BASE"
    )
    openai_model_name: str = Field(
        default="gpt-4o",
        description="Model name to use with OpenAI or compatible provider",
        alias="OPENAI_MODEL_NAME"
    )

    # ===========================================
    # Anthropic Configuration
    # ===========================================
    anthropic_api_key: Optional[str] = Field(
        default=None,
        description="API Key for Anthropic",
        alias="ANTHROPIC_API_KEY"
    )
    anthropic_model_name: str = Field(
        default="claude-3-5-sonnet-latest",
        description="Model name for Anthropic",
        alias="ANTHROPIC_MODEL_NAME"
    )

    # ===========================================
    # Claude Web Configuration
    # ===========================================
    claude_web_timeout_seconds: int = Field(
        default=120,
        description="Timeout in seconds for Claude Web requests",
        alias="CLAUDE_WEB_TIMEOUT_SECONDS"
    )
    claude_web_model_name: str = Field(
        default="claude-3-5-sonnet-20240620",
        description="Model name for Claude Web",
        alias="CLAUDE_WEB_MODEL_NAME"
    )
    claude_web_endpoint: str = Field(
        default="http://localhost:8001/api/claude/direct",
        description="Endpoint for Claude Web (internal proxy API)",
        alias="CLAUDE_WEB_ENDPOINT"
    )

    # ===========================================
    # DeepSeek Configuration
    # ===========================================
    deepseek_api_key: Optional[str] = Field(
        default=None,
        description="API Key for DeepSeek",
        alias="DEEPSEEK_API_KEY"
    )
    deepseek_model_name: str = Field(
        default="deepseek-chat",
        description="Model name for DeepSeek (e.g., deepseek-chat, deepseek-reasoner)",
        alias="DEEPSEEK_MODEL_NAME"
    )
    # ===========================================
    # Agent Behavior Configuration
    # ===========================================
    scan_interval_minutes: int = Field(
        default=15,
        description="How often to run the observation cycle",
        alias="SCAN_INTERVAL_MINUTES"
    )
    rolling_window_hours: int = Field(
        default=6,
        description="Hours of audit logs to consider for context",
        alias="ROLLING_WINDOW_HOURS"
    )
    max_actions_per_hour: int = Field(
        default=50,
        description="Safety limit on actions per hour",
        alias="MAX_ACTIONS_PER_HOUR"
    )
    action_cooldown_minutes: int = Field(
        default=60,
        description="How long to wait before repeating an action on the same target",
        alias="ACTION_COOLDOWN_MINUTES"
    )
    failure_streak_threshold: int = Field(
        default=3,
        description="Number of failures before triggering self-correction",
        alias="FAILURE_STREAK_THRESHOLD"
    )
    human_approval_required: bool = Field(
        default=False,
        description="Require human approval for critical actions",
        alias="HUMAN_APPROVAL_REQUIRED"
    )
    social_pulse_enabled: bool = Field(
        default=True,
        description="Enable/disable the brain's natural social drive",
        alias="SOCIAL_PULSE_ENABLED"
    )
    social_pulse_chance: float = Field(
        default=0.1,
        description="Probability of triggering a social impulse (0.0 to 1.0)",
        alias="SOCIAL_PULSE_CHANCE"
    )
    
    # --- Context Limits (Phase 21.5) ---
    context_planning_limit: int = Field(
        default=20,
        description="Number of recent messages used for routing and planning",
        alias="CONTEXT_PLANNING_LIMIT"
    )
    context_generation_limit: int = Field(
        default=100,
        description="Number of recent messages used for final response generation",
        alias="CONTEXT_GENERATION_LIMIT"
    )
    context_compression_chars: int = Field(
        default=5000,
        description="Threshold in characters to trigger context compression",
        alias="CONTEXT_COMPRESSION_CHARS"
    )
    context_compression_messages: int = Field(
        default=30,
        description="Threshold in message count to trigger context compression",
        alias="CONTEXT_COMPRESSION_MESSAGES"
    )

    # ===========================================
    # MCP Configuration
    # ===========================================
    mcp_config_path: str = Field(
        default="config/mcp_servers.json",
        description="Path to JSON file containing MCP server definitions",
        alias="MCP_CONFIG_PATH"
    )
    mcp_servers: dict = Field(
        default_factory=dict,
        description="Configuration for MCP Servers (command, args, env)",
        alias="MCP_SERVERS"
    )
    
    mailbox_auth_token: str = Field(
        default="niva-mailbox-dev-token-2026",
        description="Authentication token for the Mailbox MCP server",
        alias="MAILBOX_AUTH_TOKEN"
    )
    
    # ===========================================
    # Tavily Configuration
    # ===========================================
    tavily_api_key: str = Field(
        default="",
        description="API key for Tavily",
        alias="TAVILY_API_KEY"
    )
    
    # ===========================================
    # Security & Encryption Configuration
    # ===========================================
    memory_key: Optional[str] = Field(
        default=None,
        description="Encryption key for agent memory",
        alias="MEMORY_KEY"
    )

    # ===========================================
    # Resend Email Configuration
    # ===========================================
    resend_api_key: Optional[str] = Field(
        default=None,
        description="API Key for Resend",
        alias="RESEND_API_KEY"
    )
    resend_from_email: str = Field(
        default="onboarding@resend.dev",
        description="Sender email for Resend",
        alias="RESEND_FROM_EMAIL"
    )

    def model_post_init(self, __context):
        """Load and merge MCP config from JSON after initialization"""
        import json
        
        # Determine absolute path for config
        config_path = Path(self.mcp_config_path)
        if not config_path.is_absolute():
            # Try relative to the app root (where main.py typically is)
            root_dir = Path(__file__).parent.parent
            config_path = root_dir / self.mcp_config_path

        if config_path.exists():
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    external_config = json.load(f)
                    
                    # FLEXIBLE RESOLUTION: Check if it's nested under 'mcp_servers', 'mcpServers', or directly at root
                    json_servers = external_config.get("mcp_servers") or external_config.get("mcpServers")
                    
                    if json_servers is None:
                        # If not in key, then the whole file might be the dict
                        json_servers = external_config if isinstance(external_config, dict) else {}

                    # Merge JSON config into mcp_servers dictionary
                    for name, config in json_servers.items():
                        if name not in self.mcp_servers:
                            self.mcp_servers[name] = config
                            
            except Exception as e:
                print(f"[SETTINGS] Warning: Failed to load MCP config from {config_path}: {e}")
    
    # ===========================================
    # Logging Configuration
    # ===========================================
    log_level: str = Field(
        default="INFO",
        description="Logging level",
        alias="LOG_LEVEL"
    )
    log_dir: str = Field(
        default="./logs",
        description="Directory for log files",
        alias="LOG_DIR"
    )
    
    # ===========================================
    # Notification Configuration (Optional)
    # ===========================================
    telegram_bot_token: Optional[str] = Field(
        default=None,
        description="Telegram bot token for notifications",
        alias="TELEGRAM_BOT_TOKEN"
    )
    telegram_chat_id: Optional[str] = Field(
        default=None,
        description="Telegram chat ID for admin notifications",
        alias="TELEGRAM_CHAT_ID"
    )
    telegram_polling_timeout: int = Field(
        default=30,
        description="Long polling timeout for Telegram getUpdates (seconds)",
        alias="TELEGRAM_POLLING_TIMEOUT"
    )
    
    # Dynamic Identity (Runtime)
    bot_name: str = "Karatos (Brain)"
    bot_username: Optional[str] = None
    user_pronoun: str = "Anh"
    bot_pronoun: str = "Em"
    
    @property
    def telegram_admin_chat_id(self) -> Optional[str]:
        """Alias for telegram_chat_id for clearer naming"""
        return self.telegram_chat_id

    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False
        extra = "ignore"
    
    @property
    def agent_log_path(self) -> Path:
        """Get the path for agent logs"""
        log_path = Path(self.log_dir)
        log_path.mkdir(parents=True, exist_ok=True)
        return log_path
    
    def validate_required(self) -> bool:
        """Validate that all required settings are configured"""
        required_fields = [
            ("database_url", self.database_url),
        ]
        
        missing = [name for name, value in required_fields if not value]
        
        if missing:
            raise ValueError(f"Missing required configuration: {', '.join(missing)}")
        
    def save_to_env(self, updates: dict):
        """Update .env file with new values and reload current settings."""
        env_path = Path(self.Config.env_file)
        if not env_path.exists():
            # Create if doesn't exist
            with open(env_path, "w", encoding="utf-8") as f:
                f.write("# Karatos Environment Configuration\n")

        # Read existing content
        with open(env_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        # Update or add new variables
        updated_keys = set()
        new_lines = []
        
        for line in lines:
            if "=" in line and not line.strip().startswith("#"):
                key = line.split("=")[0].strip()
                if key in updates:
                    new_lines.append(f"{key}={updates[key]}\n")
                    updated_keys.add(key)
                    continue
            new_lines.append(line)

        # Append new keys that weren't in the file
        for key, value in updates.items():
            if key not in updated_keys:
                if new_lines and not new_lines[-1].endswith("\n"):
                    new_lines.append("\n")
                new_lines.append(f"{key}={value}\n")

        # Write back to file
        with open(env_path, "w", encoding="utf-8") as f:
            f.writelines(new_lines)
            
        print(f"[SETTINGS] Saved {len(updates)} variables to {self.Config.env_file}")
        
        # Optionally: In a real app we might want to reload the Pydantic model here
        # or just rely on the next process start. For now, we update the current instance.
        for key, value in updates.items():
            # Find the alias for the field
            for field_name, field in self.model_fields.items():
                if field.alias == key or field_name == key:
                    setattr(self, field_name, value)
                    break


# Singleton instance
settings = Settings()
