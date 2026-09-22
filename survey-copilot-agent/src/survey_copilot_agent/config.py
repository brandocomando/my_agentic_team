from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="SURVEY_COPILOT_",
        extra="ignore",
    )

    host: str = "127.0.0.1"
    port: int = 8765
    db_path: Path = Path("data/memory.sqlite")
    profile_path: Path = Path("config/profile.local.json")
    ollama_base_url: str = Field("http://localhost:11434", validation_alias="OLLAMA_BASE_URL")
    ollama_chat_model: str = Field("llama3.1:8b", validation_alias="OLLAMA_CHAT_MODEL")
    ollama_embed_model: str = Field("nomic-embed-text", validation_alias="OLLAMA_EMBED_MODEL")
    answer_min_confidence: float = Field(0.62, validation_alias="ANSWER_MIN_CONFIDENCE")
    use_laya: bool = Field(True, validation_alias="USE_LAYA")
    laya_min_confidence: float = Field(0.70, validation_alias="LAYA_MIN_CONFIDENCE")
    laya_model_name: str = Field("convaiinnovations/laya", validation_alias="LAYA_MODEL_NAME")


@lru_cache
def get_settings() -> Settings:
    return Settings()
