from __future__ import annotations

from pathlib import Path

import yaml
from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from campsite_finder_agent.models import AppConfig


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore", env_ignore_empty=True)

    config_path: Path = Field(default=Path("./config/searches.yaml"), alias="CAMPSITE_CONFIG_PATH")
    output_path: Path = Field(default=Path("./data/matches.json"), alias="CAMPSITE_OUTPUT_PATH")
    csv_output_path: Path = Field(default=Path("./data/matches.csv"), alias="CAMPSITE_CSV_OUTPUT_PATH")
    lock_output_path: Path = Field(default=Path("./data/locked-matches.json"), alias="CAMPSITE_LOCK_OUTPUT_PATH")
    lock_csv_output_path: Path = Field(default=Path("./data/locked-matches.csv"), alias="CAMPSITE_LOCK_CSV_OUTPUT_PATH")
    cache_path: Path = Field(default=Path("./data/cache"), alias="CAMPSITE_CACHE_PATH")
    raw_data_path: Path = Field(default=Path("./data/raw"), alias="CAMPSITE_RAW_DATA_PATH")
    state_path: Path = Field(default=Path("./data/state.json"), alias="CAMPSITE_STATE_PATH")
    cdp_url: str = Field(default="http://localhost:9222", alias="CAMPSITE_CDP_URL")
    login_timeout_ms: int = Field(default=300_000, alias="CAMPSITE_LOGIN_TIMEOUT_MS")
    request_delay_seconds: float = Field(default=2.5, alias="CAMPSITE_REQUEST_DELAY_SECONDS")
    search_delay_seconds: float = Field(default=8.0, alias="CAMPSITE_SEARCH_DELAY_SECONDS")
    max_retries: int = Field(default=4, alias="CAMPSITE_MAX_RETRIES")
    get_site_site: str = Field(default="", alias="CAMPSITE_GET_SITE_SITE")
    get_site_start_date: str = Field(default="", alias="CAMPSITE_GET_SITE_START_DATE")
    get_site_nights: int | None = Field(default=None, alias="CAMPSITE_GET_SITE_NIGHTS")
    get_site_campground_url: str = Field(default="", alias="CAMPSITE_GET_SITE_CAMPGROUND_URL")
    get_site_occupant: str = Field(default="", alias="CAMPSITE_GET_SITE_OCCUPANT")
    get_site_occupant_name: str = Field(default="", alias="CAMPSITE_GET_SITE_OCCUPANT_NAME")
    get_site_adults: int = Field(default=2, alias="CAMPSITE_GET_SITE_ADULTS")
    get_site_children: int = Field(default=2, alias="CAMPSITE_GET_SITE_CHILDREN")
    get_site_camping_unit: str = Field(default="Trailer", alias="CAMPSITE_GET_SITE_CAMPING_UNIT")
    get_site_trailer_length_feet: float | None = Field(default=None, alias="CAMPSITE_GET_SITE_TRAILER_LENGTH_FEET")
    get_site_vehicle_count: int | None = Field(default=None, alias="CAMPSITE_GET_SITE_VEHICLE_COUNT")
    get_site_phone_number: str = Field(default="", alias="CAMPSITE_GET_SITE_PHONE_NUMBER")
    get_site_street_1: str = Field(default="", alias="CAMPSITE_GET_SITE_STREET_1")
    get_site_city: str = Field(default="", alias="CAMPSITE_GET_SITE_CITY")
    get_site_state: str = Field(default="", alias="CAMPSITE_GET_SITE_STATE")
    get_site_postal_code: str = Field(default="", alias="CAMPSITE_GET_SITE_POSTAL_CODE")
    get_site_zipcode: str = Field(default="", alias="CAMPSITE_GET_SITE_ZIPCODE")
    get_site_refresh_window_start: str = Field(default="07:59:30", alias="CAMPSITE_GET_SITE_REFRESH_WINDOW_START")
    get_site_refresh_window_end: str = Field(default="08:01:00", alias="CAMPSITE_GET_SITE_REFRESH_WINDOW_END")
    get_site_refresh_timezone: str = Field(default="America/Los_Angeles", alias="CAMPSITE_GET_SITE_REFRESH_TIMEZONE")
    get_site_refresh_interval_seconds: float = Field(default=1.0, alias="CAMPSITE_GET_SITE_REFRESH_INTERVAL_SECONDS")
    get_site_max_run_seconds: float | None = Field(default=None, alias="CAMPSITE_GET_SITE_MAX_RUN_SECONDS")
    ollama_base_url: str = Field(default="http://localhost:11434", alias="OLLAMA_BASE_URL")
    ollama_model: str = Field(default="llama3.1", alias="OLLAMA_MODEL")
    outdoorithm_api_key: str = Field(default="", alias="OUTDOORITHM_API_KEY")
    email_alerts_enabled: bool = Field(default=False, alias="CAMPSITE_EMAIL_ALERTS_ENABLED")
    gmail_credentials_path: Path = Field(default=Path("./data/gmail_credentials.json"), alias="GMAIL_CREDENTIALS_PATH")
    gmail_token_path: Path = Field(default=Path("./data/gmail_token.json"), alias="GMAIL_TOKEN_PATH")
    email_to: str = Field(default="", alias="CAMPSITE_EMAIL_TO")
    ai_notify_min_score: float = Field(default=8.0, alias="CAMPSITE_AI_NOTIFY_MIN_SCORE")
    ai_notify_actions: str = Field(default="book", alias="CAMPSITE_AI_NOTIFY_ACTIONS")
    notification_state_path: Path = Field(default=Path("./data/notifications.json"), alias="CAMPSITE_NOTIFICATION_STATE_PATH")


def load_settings() -> Settings:
    load_dotenv(override=True)
    settings = Settings()
    settings.output_path.parent.mkdir(parents=True, exist_ok=True)
    settings.csv_output_path.parent.mkdir(parents=True, exist_ok=True)
    settings.lock_output_path.parent.mkdir(parents=True, exist_ok=True)
    settings.lock_csv_output_path.parent.mkdir(parents=True, exist_ok=True)
    settings.cache_path.mkdir(parents=True, exist_ok=True)
    settings.gmail_token_path.parent.mkdir(parents=True, exist_ok=True)
    settings.notification_state_path.parent.mkdir(parents=True, exist_ok=True)
    return settings


def load_config(path: Path) -> AppConfig:
    if not path.exists():
        raise FileNotFoundError(
            f"Config file not found: {path}. Copy config/searches.example.yaml to config/searches.yaml."
        )
    with path.open() as handle:
        payload = yaml.safe_load(handle) or {}
    config = AppConfig.model_validate(payload)
    if config.filters != config.filters.__class__():
        config.searches = [
            search.model_copy(update={"filters": config.filters.merged_with(search.filters)})
            for search in config.searches
        ]
        config.locked_searches = [
            search.model_copy(update={"filters": config.filters.merged_with(search.filters)})
            for search in config.locked_searches
        ]
    return config
