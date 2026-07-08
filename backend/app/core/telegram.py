from pathlib import Path

from telethon import TelegramClient

from app.core.config import get_settings


settings = get_settings()
Path(settings.session_dir).mkdir(parents=True, exist_ok=True)


def build_client(session_name: str) -> TelegramClient:
    session_path = str(Path(settings.session_dir) / session_name)
    return TelegramClient(session_path, settings.telegram_api_id, settings.telegram_api_hash)
