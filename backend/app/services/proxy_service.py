import socket
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.proxy import ProxyConfig
from app.models.session import TelegramSession


class ProxyService:
    def list_proxies(self, db: Session, owner_id: int | None = None) -> list[ProxyConfig]:
        stmt = select(ProxyConfig).order_by(ProxyConfig.is_active.desc(), ProxyConfig.updated_at.desc())
        if owner_id is not None:
            stmt = stmt.where(ProxyConfig.owner_id == owner_id)
        return list(db.scalars(stmt).all())

    def create_proxy(self, db: Session, data: dict[str, Any], owner_id: int | None = None) -> ProxyConfig:
        data["group_ids"] = self._serialize_group_ids(data.get("group_ids"))
        data["owner_id"] = owner_id
        proxy = ProxyConfig(**data)
        db.add(proxy)
        db.commit()
        db.refresh(proxy)
        return proxy

    def update_proxy(self, db: Session, proxy_id: int, data: dict[str, Any], owner_id: int | None = None) -> ProxyConfig:
        proxy = db.get(ProxyConfig, proxy_id)
        if not proxy or (owner_id is not None and proxy.owner_id != owner_id):
            raise ValueError("Proxy not found")
        if "group_ids" in data:
            data["group_ids"] = self._serialize_group_ids(data.get("group_ids"))
        for key, value in data.items():
            if hasattr(proxy, key):
                setattr(proxy, key, value)
        db.commit()
        db.refresh(proxy)
        return proxy

    def delete_proxy(self, db: Session, proxy_id: int, owner_id: int | None = None) -> None:
        proxy = db.get(ProxyConfig, proxy_id)
        if not proxy or (owner_id is not None and proxy.owner_id != owner_id):
            raise ValueError("Proxy not found")
        db.delete(proxy)
        db.commit()

    def activate_proxy(self, db: Session, proxy_id: int, owner_id: int | None = None) -> ProxyConfig:
        proxy = db.get(ProxyConfig, proxy_id)
        if not proxy or (owner_id is not None and proxy.owner_id != owner_id):
            raise ValueError("Proxy not found")
        proxy.is_active = not proxy.is_active
        db.commit()
        db.refresh(proxy)
        return proxy

    def test_proxy(self, db: Session, proxy_id: int, owner_id: int | None = None) -> ProxyConfig:
        proxy = db.get(ProxyConfig, proxy_id)
        if not proxy or (owner_id is not None and proxy.owner_id != owner_id):
            raise ValueError("Proxy not found")
        try:
            with socket.create_connection((proxy.host, proxy.port), timeout=5):
                proxy.status = "reachable"
                proxy.error_message = None
        except Exception as exc:
            proxy.status = "unreachable"
            proxy.error_message = str(exc)
        proxy.last_check_at = datetime.utcnow()
        db.commit()
        db.refresh(proxy)
        return proxy

    def get_active_proxy_url(self, db: Session) -> str | None:
        proxy = db.scalar(select(ProxyConfig).where(ProxyConfig.is_active.is_(True)).order_by(ProxyConfig.updated_at.desc()))
        return self._proxy_url(proxy)

    def get_proxy_url_for_session(self, db: Session, session: TelegramSession | None) -> str | None:
        return self._proxy_url(self.get_proxy_for_session(db, session))

    def get_proxy_for_session(self, db: Session, session: TelegramSession | None, require_active: bool = True) -> ProxyConfig | None:
        if not session:
            return None
        group_key = str(session.group_id or 0)
        stmt = select(ProxyConfig).order_by(ProxyConfig.is_active.desc(), ProxyConfig.updated_at.desc())
        stmt = stmt.where(ProxyConfig.owner_id == session.owner_id)
        if require_active:
            stmt = stmt.where(ProxyConfig.is_active.is_(True))
        proxies = db.scalars(stmt).all()
        for proxy in proxies:
            if group_key in self._deserialize_group_ids(proxy.group_ids):
                return proxy
        return None

    def assign_sessions(self, db: Session, session_ids: list[int], proxy_id: int | None, owner_id: int | None = None) -> int:
        stmt = select(TelegramSession).where(TelegramSession.id.in_(session_ids))
        if owner_id is not None:
            stmt = stmt.where(TelegramSession.owner_id == owner_id)
        sessions = db.scalars(stmt).all()
        group_ids = list(dict.fromkeys(str(session.group_id or 0) for session in sessions))
        proxy_stmt = select(ProxyConfig)
        if owner_id is not None:
            proxy_stmt = proxy_stmt.where(ProxyConfig.owner_id == owner_id)
        proxies = list(db.scalars(proxy_stmt).all())
        for proxy in proxies:
            current = [item for item in self._deserialize_group_ids(proxy.group_ids) if item not in group_ids]
            proxy.group_ids = ",".join(current) if current else None

        if proxy_id and proxy_id != 0:
            proxy = db.get(ProxyConfig, proxy_id)
            if not proxy or (owner_id is not None and proxy.owner_id != owner_id):
                raise ValueError("Proxy not found")
            current = self._deserialize_group_ids(proxy.group_ids)
            proxy.group_ids = ",".join(list(dict.fromkeys([*current, *group_ids])))

        db.commit()
        return len(group_ids)

    def _proxy_url(self, proxy: ProxyConfig | None) -> str | None:
        if not proxy:
            return None
        auth = ""
        if proxy.username:
            auth = proxy.username
            if proxy.password:
                auth += f":{proxy.password}"
            auth += "@"
        return f"{proxy.scheme}://{auth}{proxy.host}:{proxy.port}"

    def serialize_proxy(self, proxy: ProxyConfig) -> dict[str, Any]:
        return {
            "id": proxy.id,
            "name": proxy.name,
            "scheme": proxy.scheme,
            "host": proxy.host,
            "port": proxy.port,
            "username": proxy.username,
            "password": proxy.password,
            "color": proxy.color,
            "is_active": proxy.is_active,
            "group_ids": [int(item) for item in self._deserialize_group_ids(proxy.group_ids) if item.isdigit()],
            "session_ids": [int(item) for item in self._deserialize_ids(proxy.session_ids) if item.isdigit()],
            "status": proxy.status,
            "error_message": proxy.error_message,
            "last_check_at": proxy.last_check_at.isoformat() if proxy.last_check_at else None,
            "created_at": proxy.created_at.isoformat() if proxy.created_at else None,
            "updated_at": proxy.updated_at.isoformat() if proxy.updated_at else None,
        }

    def _serialize_group_ids(self, value: Any) -> str | None:
        if value is None:
            return None
        if isinstance(value, str):
            parts = [item.strip() for item in value.split(",") if item.strip()]
        else:
            parts = [str(item) for item in value if item is not None]
        normalized = list(dict.fromkeys(parts))
        return ",".join(normalized) if normalized else None

    def _deserialize_group_ids(self, value: str | None) -> list[str]:
        return self._deserialize_ids(value)

    def _deserialize_ids(self, value: str | None) -> list[str]:
        if not value:
            return []
        return [item for item in value.split(",") if item]


proxy_service = ProxyService()
