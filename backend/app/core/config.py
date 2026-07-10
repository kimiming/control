from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "TG Marketing System"
    api_prefix: str = "/api"
    database_url: str = "sqlite:///./tg_marketing.db"
    redis_url: str = "redis://localhost:6379/0"
    telegram_api_id: int = 0
    telegram_api_hash: str = ""
    telegram_proxy_url: str | None = None
    session_dir: str = "./telegram_sessions"
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]
    health_check_interval_seconds: int = 60

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


@lru_cache
def get_settings() -> Settings:
    return Settings()
