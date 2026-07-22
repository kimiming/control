from urllib.parse import quote

import socks
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.proxy import ProxyConfig
from app.models.session import TelegramSession
from app.core.telegram import build_proxy


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
        sock = socks.socksocket()
        sock.settimeout(10)
        try:
            proxy_args = build_proxy(self._proxy_url(proxy))
            if proxy_args is None:
                raise ValueError("代理配置格式无效")
            sock.set_proxy(*proxy_args)
            sock.connect(("149.154.167.51", 443))
            proxy.status = "reachable"
            proxy.error_message = None
        except Exception as exc:
            proxy.status = "unreachable"
            proxy.error_message = f"代理无法连接Telegram: {exc}"
        finally:
            sock.close()
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
        session_key = str(session.id)
        for proxy in proxies:
            if session_key in self._deserialize_ids(proxy.session_ids):
                return proxy
        for proxy in proxies:
            if group_key in self._deserialize_group_ids(proxy.group_ids):
                return proxy
        return None

    def get_proxy_map_for_sessions(
        self,
        db: Session,
        sessions: list[TelegramSession],
        require_active: bool = True,
    ) -> dict[int, ProxyConfig]:
        """Resolve a page of Session proxies with one proxy query."""
        if not sessions:
            return {}
        owner_ids = {session.owner_id for session in sessions}
        stmt = select(ProxyConfig).where(ProxyConfig.owner_id.in_(owner_ids)).order_by(
            ProxyConfig.is_active.desc(), ProxyConfig.updated_at.desc()
        )
        if require_active:
            stmt = stmt.where(ProxyConfig.is_active.is_(True))
        proxies = list(db.scalars(stmt).all())
        direct: dict[str, ProxyConfig] = {}
        grouped: dict[tuple[int | None, str], ProxyConfig] = {}
        for proxy in proxies:
            for session_id in self._deserialize_ids(proxy.session_ids):
                direct.setdefault(session_id, proxy)
            for group_id in self._deserialize_group_ids(proxy.group_ids):
                grouped.setdefault((proxy.owner_id, group_id), proxy)
        result: dict[int, ProxyConfig] = {}
        for session in sessions:
            proxy = direct.get(str(session.id)) or grouped.get((session.owner_id, str(session.group_id or 0)))
            if proxy:
                result[session.id] = proxy
        return result

    def assign_sessions(self, db: Session, session_ids: list[int], proxy_id: int | None, owner_id: int | None = None) -> int:
        stmt = select(TelegramSession).where(TelegramSession.id.in_(session_ids))
        if owner_id is not None:
            stmt = stmt.where(TelegramSession.owner_id == owner_id)
        sessions = db.scalars(stmt).all()
        selected_ids = {str(session.id) for session in sessions}
        proxy_stmt = select(ProxyConfig)
        if owner_id is not None:
            proxy_stmt = proxy_stmt.where(ProxyConfig.owner_id == owner_id)
        proxies = list(db.scalars(proxy_stmt).all())
        for proxy in proxies:
            current = [item for item in self._deserialize_ids(proxy.session_ids) if item not in selected_ids]
            proxy.session_ids = ",".join(current) if current else None

        if proxy_id and proxy_id != 0:
            proxy = db.get(ProxyConfig, proxy_id)
            if not proxy or (owner_id is not None and proxy.owner_id != owner_id):
                raise ValueError("Proxy not found")
            current = self._deserialize_ids(proxy.session_ids)
            proxy.session_ids = ",".join(list(dict.fromkeys([*current, *selected_ids])))

        db.commit()
        return len(sessions)

    def _proxy_url(self, proxy: ProxyConfig | None) -> str | None:
        if not proxy:
            return None
        auth = ""
        if proxy.username:
            auth = quote(proxy.username, safe='')
            if proxy.password:
                auth += f":{quote(proxy.password, safe='')}"
            auth += "@"
        host = f"[{proxy.host}]" if ":" in proxy.host and not proxy.host.startswith("[") else proxy.host
        return f"{proxy.scheme}://{auth}{host}:{proxy.port}"

    def serialize_proxy(self, proxy: ProxyConfig, db: Session | None = None) -> dict[str, Any]:
        configured_group_ids = self._deserialize_group_ids(proxy.group_ids)
        bound_group_ids = list(configured_group_ids)
        session_ids = [int(item) for item in self._deserialize_ids(proxy.session_ids) if item.isdigit()]
        if db is not None and session_ids:
            stmt = select(TelegramSession.group_id).where(TelegramSession.id.in_(session_ids))
            if proxy.owner_id is not None:
                stmt = stmt.where(TelegramSession.owner_id == proxy.owner_id)
            session_group_ids = [str(group_id or 0) for group_id in db.scalars(stmt).all()]
            bound_group_ids = list(dict.fromkeys([*bound_group_ids, *session_group_ids]))
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
            "group_ids": [int(item) for item in configured_group_ids if item.isdigit()],
            "bound_group_ids": [int(item) for item in bound_group_ids if item.isdigit()],
            "session_ids": session_ids,
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
