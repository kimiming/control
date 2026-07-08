import asyncio
import csv
import io
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import UploadFile
from openpyxl import load_workbook
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.telegram import build_client
from app.models.session import SessionGroup, SessionLog, SessionStatus, TelegramSession
from app.services.websocket_manager import session_ws_manager


settings = get_settings()


class SessionService:
    def list_sessions(self, db: Session, group_id: int | None = None) -> list[TelegramSession]:
        stmt = select(TelegramSession).order_by(TelegramSession.updated_at.desc())
        if group_id:
            stmt = stmt.where(TelegramSession.group_id == group_id)
        return list(db.scalars(stmt).all())

    def create_session(self, db: Session, data: dict[str, Any]) -> TelegramSession:
        session = TelegramSession(
            username=data["username"],
            avatar=data.get("avatar"),
            phone=data["phone"],
            session_name=data.get("session_name") or self._make_session_name(data["phone"]),
            group_id=data.get("group_id"),
        )
        db.add(session)
        db.flush()
        self.log(db, session.id, "create", "Session created")
        db.commit()
        db.refresh(session)
        return session

    async def update_session(self, db: Session, session_id: int, data: dict[str, Any]) -> TelegramSession:
        session = db.get(TelegramSession, session_id)
        if not session:
            raise ValueError("Session not found")

        action = data.pop("action", None)
        for key, value in data.items():
            if hasattr(session, key) and value is not None:
                setattr(session, key, value)

        if action == "connect":
            await self.connect_session(db, session)
        elif action == "disconnect":
            await self.disconnect_session(db, session)
        else:
            self.log(db, session.id, "update", "Session updated")
            db.commit()
            db.refresh(session)
            await self.publish_status(session, "updated")
        return session

    async def connect_session(self, db: Session, session: TelegramSession) -> TelegramSession:
        session.status = SessionStatus.connecting
        session.error_message = None
        db.commit()
        db.refresh(session)
        await self.publish_status(session, "status_changed")

        try:
            client = build_client(session.session_name)
            await client.connect()
            if not await client.is_user_authorized():
                raise RuntimeError("Telegram session is not authorized. Import or authorize the session file first.")

            me = await client.get_me()
            session.username = me.username or session.username
            session.phone = me.phone or session.phone
            session.status = SessionStatus.connected
            session.last_login_at = datetime.utcnow()
            session.health_status = "healthy"
            session.error_message = None
            self.log(db, session.id, "connect", "Session connected")
            await client.disconnect()
        except Exception as exc:
            session.status = SessionStatus.error
            session.health_status = "unhealthy"
            session.error_message = str(exc)
            self.log(db, session.id, "connect_failed", str(exc))

        db.commit()
        db.refresh(session)
        await self.publish_status(session, "status_changed")
        return session

    async def disconnect_session(self, db: Session, session: TelegramSession) -> TelegramSession:
        try:
            client = build_client(session.session_name)
            if client.is_connected():
                await client.disconnect()
        except Exception:
            pass

        session.status = SessionStatus.disconnected
        session.health_status = "unknown"
        self.log(db, session.id, "disconnect", "Session disconnected")
        db.commit()
        db.refresh(session)
        await self.publish_status(session, "status_changed")
        return session

    async def delete_session(self, db: Session, session_id: int) -> None:
        session = db.get(TelegramSession, session_id)
        if not session:
            raise ValueError("Session not found")
        session_file = Path(settings.session_dir) / f"{session.session_name}.session"
        db.delete(session)
        db.commit()
        if session_file.exists():
            session_file.unlink()
        await session_ws_manager.broadcast("*", {"event": "deleted", "id": session_id})

    def list_groups(self, db: Session) -> list[SessionGroup]:
        return list(db.scalars(select(SessionGroup).order_by(SessionGroup.name)).all())

    def create_group(self, db: Session, name: str, description: str | None = None) -> SessionGroup:
        group = SessionGroup(name=name, description=description)
        db.add(group)
        db.commit()
        db.refresh(group)
        return group

    async def move_sessions(self, db: Session, session_ids: list[int], group_id: int | None) -> int:
        sessions = db.scalars(select(TelegramSession).where(TelegramSession.id.in_(session_ids))).all()
        for session in sessions:
            session.group_id = group_id
            self.log(db, session.id, "move_group", f"Moved to group {group_id or 'none'}")
        db.commit()
        for session in sessions:
            db.refresh(session)
            await self.publish_status(session, "updated")
        return len(sessions)

    async def import_sessions(self, db: Session, file: UploadFile) -> dict[str, int]:
        content = await file.read()
        rows = self._read_import_rows(file.filename or "", content)
        created = 0
        skipped = 0
        for row in rows:
            phone = str(row.get("phone", "")).strip()
            username = str(row.get("username", "")).strip()
            if not phone or not username:
                skipped += 1
                continue
            exists = db.scalar(select(TelegramSession).where(TelegramSession.phone == phone))
            if exists:
                skipped += 1
                continue
            self.create_session(db, {"username": username, "phone": phone, "avatar": row.get("avatar"), "group_id": row.get("group_id")})
            created += 1
        await session_ws_manager.broadcast("*", {"event": "bulk_imported", "created": created, "skipped": skipped})
        return {"created": created, "skipped": skipped}

    async def health_check_once(self, db: Session) -> dict[str, int]:
        sessions = db.scalars(select(TelegramSession)).all()
        checked = 0
        for session in sessions:
            checked += 1
            try:
                client = build_client(session.session_name)
                await client.connect()
                authorized = await client.is_user_authorized()
                session.status = SessionStatus.connected if authorized else SessionStatus.disconnected
                session.health_status = "healthy" if authorized else "unauthorized"
                session.last_health_check_at = datetime.utcnow()
                await client.disconnect()
            except Exception as exc:
                session.status = SessionStatus.error
                session.health_status = "unhealthy"
                session.error_message = str(exc)
                session.last_health_check_at = datetime.utcnow()
            self.log(db, session.id, "health_check", session.health_status or "unknown")
            db.commit()
            db.refresh(session)
            await self.publish_status(session, "status_changed")
        return {"checked": checked}

    def list_logs(self, db: Session, session_id: int | None = None, limit: int = 100) -> list[SessionLog]:
        stmt = select(SessionLog).order_by(SessionLog.created_at.desc()).limit(limit)
        if session_id:
            stmt = stmt.where(SessionLog.session_id == session_id)
        return list(db.scalars(stmt).all())

    def log(self, db: Session, session_id: int | None, action: str, message: str) -> None:
        db.add(SessionLog(session_id=session_id, action=action, message=message))

    async def publish_status(self, session: TelegramSession, event: str) -> None:
        payload = {"event": event, "session": self.serialize_session(session)}
        await session_ws_manager.broadcast(str(session.id), payload)
        await session_ws_manager.broadcast("*", payload)

    def serialize_session(self, session: TelegramSession) -> dict[str, Any]:
        return {
            "id": session.id,
            "username": session.username,
            "avatar": session.avatar,
            "phone": session.phone,
            "session_name": session.session_name,
            "status": session.status.value if hasattr(session.status, "value") else session.status,
            "last_login_at": session.last_login_at.isoformat() if session.last_login_at else None,
            "last_health_check_at": session.last_health_check_at.isoformat() if session.last_health_check_at else None,
            "health_status": session.health_status,
            "error_message": session.error_message,
            "group_id": session.group_id,
            "group_name": session.group.name if session.group else None,
            "created_at": session.created_at.isoformat() if session.created_at else None,
            "updated_at": session.updated_at.isoformat() if session.updated_at else None,
        }

    def _make_session_name(self, phone: str) -> str:
        return "tg_" + "".join(ch for ch in phone if ch.isalnum())

    def _read_import_rows(self, filename: str, content: bytes) -> list[dict[str, Any]]:
        if filename.lower().endswith(".csv"):
            text = content.decode("utf-8-sig")
            return list(csv.DictReader(io.StringIO(text)))

        workbook = load_workbook(io.BytesIO(content), read_only=True)
        sheet = workbook.active
        rows = list(sheet.iter_rows(values_only=True))
        if not rows:
            return []
        headers = [str(cell).strip() for cell in rows[0]]
        return [dict(zip(headers, row)) for row in rows[1:]]


session_service = SessionService()


async def health_check_loop() -> None:
    while True:
        await asyncio.sleep(settings.health_check_interval_seconds)
        from app.core.database import SessionLocal

        db = SessionLocal()
        try:
            await session_service.health_check_once(db)
        finally:
            db.close()
