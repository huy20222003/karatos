from pydantic_settings import BaseSettings, SettingsConfigDict
from pathlib import Path

# Resolve the .env file path
DOTENV_PATH = Path(__file__).parent.parent / ".env"

class Settings(BaseSettings):
    # Server identity
    mailbox_server_name: str = "Mailbox"
    
    # Network settings
    mailbox_port: int = 8000
    mailbox_host: str = "127.0.0.1"
    
    # Logic settings
    mailbox_max_messages_per_bot: int = 100

    # Pydantic Settings configuration
    model_config = SettingsConfigDict(
        env_file=DOTENV_PATH,
        env_file_encoding='utf-8',
        case_sensitive=False
    )

    @property
    def SERVER_NAME(self) -> str:
        return self.mailbox_server_name
    
    @property
    def PORT(self) -> int:
        return self.mailbox_port
    
    @property
    def HOST(self) -> str:
        return self.mailbox_host
    
    @property
    def MAX_MESSAGES_PER_BOT(self) -> int:
        return self.mailbox_max_messages_per_bot

settings = Settings()
