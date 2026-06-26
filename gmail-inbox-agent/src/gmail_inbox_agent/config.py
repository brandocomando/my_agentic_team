from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    openai_api_key: str = Field(default="", alias="OPENAI_API_KEY")
    gmail_credentials_path: Path = Field(
        default=Path("./data/gmail_credentials.json"), alias="GMAIL_CREDENTIALS_PATH"
    )
    gmail_token_path: Path = Field(default=Path("./data/gmail_token.json"), alias="GMAIL_TOKEN_PATH")
    memory_db_path: Path = Field(default=Path("./data/memory.sqlite"), alias="MEMORY_DB_PATH")
    user_email: str = Field(default="", alias="USER_EMAIL")
    dry_run: bool = Field(default=True, alias="DRY_RUN")
    max_messages_per_run: int = Field(default=25, alias="MAX_MESSAGES_PER_RUN", ge=1)


def load_settings() -> Settings:
    load_dotenv()
    settings = Settings()
    settings.memory_db_path.parent.mkdir(parents=True, exist_ok=True)
    settings.gmail_token_path.parent.mkdir(parents=True, exist_ok=True)
    return settings
