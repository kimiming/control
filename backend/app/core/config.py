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
    task_global_concurrency: int = 20
    task_session_window: int = 20
    task_session_lock_seconds: int = 300
    session_max_active_clients: int = 200
    app_role: str = "api"
    session_worker_index: int = 0
    session_worker_count: int = 1
    session_connect_concurrency: int = 15
    session_owner_lock_seconds: int = 90
    session_startup_history_sync: bool = False
    session_history_sync_days: int = 2
    # A Telegram connect + authorization handshake may legitimately take close
    # to 40 seconds (20 seconds for each phase).
    session_client_wait_seconds: int = 45
    inbound_stream_name: str = "telegram:incoming"
    inbound_stream_group: str = "telegram-inbound-db"
    inbound_db_workers: int = 5
    inbound_stream_maxlen: int = 100000
    session_command_workers: int = 5
    session_runtime_ttl_seconds: int = 60
    enable_task_queue: bool = True

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


@lru_cache
def get_settings() -> Settings:
    return Settings()
