from pathlib import Path
from urllib.parse import unquote, urlparse

import socks
from telethon import TelegramClient

from app.core.config import get_settings


settings = get_settings()
Path(settings.session_dir).mkdir(parents=True, exist_ok=True)


def build_proxy(proxy_url: str | None = None):
    proxy_url = proxy_url or settings.telegram_proxy_url
    if not proxy_url:
        return None

    parsed = urlparse(proxy_url)
    scheme = parsed.scheme.lower()
    proxy_type = {
        "http": socks.HTTP,
        "https": socks.HTTP,
        "socks4": socks.SOCKS4,
        "socks5": socks.SOCKS5,
    }.get(scheme)
    if not proxy_type or not parsed.hostname or not parsed.port:
        return None

    username = unquote(parsed.username) if parsed.username else None
    password = unquote(parsed.password) if parsed.password else None
    return (proxy_type, parsed.hostname, parsed.port, True, username, password)


def build_client(session_name: str, proxy_url: str | None = None) -> TelegramClient:
    session_path = str(Path(settings.session_dir) / session_name)
    return TelegramClient(
        session_path,
        settings.telegram_api_id,
        settings.telegram_api_hash,
        proxy=build_proxy(proxy_url),
        auto_reconnect=True,
        connection_retries=5,
        retry_delay=1,
        timeout=10,
    )
