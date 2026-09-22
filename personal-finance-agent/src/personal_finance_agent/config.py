from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    database_path: Path = Field(default=Path("./data/finance.sqlite"), alias="FINANCE_DATABASE_PATH")
    categories_path: Path = Field(default=Path("./config/categories.yaml"), alias="CATEGORIES_PATH")
    local_categories_path: Path = Field(default=Path("./config/categories.local.yaml"), alias="LOCAL_CATEGORIES_PATH")
    imports_path: Path = Field(default=Path("./imports"), alias="IMPORTS_PATH")
    exports_path: Path = Field(default=Path("./exports"), alias="EXPORTS_PATH")
    ollama_base_url: str = Field(default="http://localhost:11434", alias="OLLAMA_BASE_URL")
    ollama_model: str = Field(default="llama3.1:8b", alias="OLLAMA_MODEL")
    low_confidence_threshold: float = Field(default=0.8, alias="LOW_CONFIDENCE_THRESHOLD")
    web_search_enabled: bool = Field(default=False, alias="WEB_SEARCH_ENABLED")
    use_laya: bool = Field(default=True, alias="USE_LAYA")
    laya_model_name: str = Field(default="convaiinnovations/laya", alias="LAYA_MODEL_NAME")
    laya_confidence_threshold: float = Field(default=0.80, alias="LAYA_CONFIDENCE_THRESHOLD")


def load_settings() -> Settings:
    load_dotenv(override=True)
    settings = Settings()
    settings.database_path.parent.mkdir(parents=True, exist_ok=True)
    settings.exports_path.mkdir(parents=True, exist_ok=True)
    (settings.exports_path / "review").mkdir(parents=True, exist_ok=True)
    return settings
