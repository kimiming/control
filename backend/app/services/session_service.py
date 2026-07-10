import asyncio
import csv
import io
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import UploadFile
from openpyxl import load_workbook
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, object_session

from app.core.config import get_settings
from app.core.telegram import build_client
from app.models.session import SessionGroup, SessionLog, SessionStatus, SessionTaskLog, TelegramSession
from app.services.proxy_service import proxy_service
from app.services.websocket_manager import session_ws_manager


settings = get_settings()


class SessionService:
    def list_sessions(
        self,
        db: Session,
        group_id: int | None = None,
        kf_id: int | None = None,
        status: str | None = None,
        health_status: str | None = None,
        keyword: str | None = None,
        owner_id: int | None = None,
    ) -> list[TelegramSession]:
        stmt = select(TelegramSession).order_by(TelegramSession.created_at.asc(), TelegramSession.id.asc())
        if owner_id is not None:
            stmt = stmt.where(TelegramSession.owner_id == owner_id)
        if group_id is not None:
            if group_id == 0:
                stmt = stmt.where(TelegramSession.group_id.is_(None))
            else:
                stmt = stmt.where(TelegramSession.group_id == group_id)
        if kf_id is not None:
            if kf_id == 0:
                stmt = stmt.where(TelegramSession.kf_id.is_(None))
            else:
                stmt = stmt.where(TelegramSession.kf_id == kf_id)
        if status:
            stmt = stmt.where(TelegramSession.status == status)
        if health_status:
            stmt = stmt.where(TelegramSession.health_status == health_status)
        if keyword:
            like = f"%{keyword}%"
            stmt = stmt.where(
                or_(
                    TelegramSession.phone.like(like),
                    TelegramSession.username.like(like),
                    TelegramSession.session_name.like(like),
                )
            )
        return list(db.scalars(stmt).all())

    def create_session(self, db: Session, data: dict[str, Any], owner_id: int | None = None) -> TelegramSession:
        session = TelegramSession(
            owner_id=owner_id,
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

    async def update_session(self, db: Session, session_id: int, data: dict[str, Any], owner_id: int | None = None) -> TelegramSession:
        session = db.get(TelegramSession, session_id)
        if not session or (owner_id is not None and session.owner_id != owner_id):
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
            client = build_client(session.session_name, proxy_service.get_proxy_url_for_session(db, session))
            await client.connect()
            if not await client.is_user_authorized():
                raise RuntimeError("Telegram session is not authorized. Import or authorize the session file first.")

            me = await client.get_me()
            await self._sync_telegram_profile(client, session, me)
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

    async def delete_session(self, db: Session, session_id: int, owner_id: int | None = None) -> None:
        session = db.get(TelegramSession, session_id)
        if not session or (owner_id is not None and session.owner_id != owner_id):
            raise ValueError("Session not found")
        session_file = Path(settings.session_dir) / f"{session.session_name}.session"
        db.delete(session)
        db.commit()
        if session_file.exists():
            session_file.unlink()
        await session_ws_manager.broadcast("*", {"event": "deleted", "id": session_id})

    def list_groups(self, db: Session, owner_id: int | None = None) -> list[SessionGroup]:
        stmt = select(SessionGroup).order_by(SessionGroup.name)
        if owner_id is not None:
            stmt = stmt.where(SessionGroup.owner_id == owner_id)
        return list(db.scalars(stmt).all())

    def get_sessions_by_ids(self, db: Session, session_ids: list[int], owner_id: int | None = None) -> list[TelegramSession]:
        if not session_ids:
            return []
        stmt = select(TelegramSession).where(TelegramSession.id.in_(session_ids))
        if owner_id is not None:
            stmt = stmt.where(TelegramSession.owner_id == owner_id)
        return list(db.scalars(stmt).all())

    def create_group(self, db: Session, name: str, description: str | None = None, color: str = "blue", owner_id: int | None = None) -> SessionGroup:
        group = SessionGroup(owner_id=owner_id, name=name, description=description, color=color or "blue")
        db.add(group)
        db.commit()
        db.refresh(group)
        return group

    async def move_sessions(self, db: Session, session_ids: list[int], group_id: int | None, owner_id: int | None = None) -> int:
        target_group_id = None if group_id == 0 else group_id
        stmt = select(TelegramSession).where(TelegramSession.id.in_(session_ids))
        if owner_id is not None:
            stmt = stmt.where(TelegramSession.owner_id == owner_id)
        sessions = db.scalars(stmt).all()
        for session in sessions:
            session.group_id = target_group_id
            self.log(db, session.id, "move_group", f"Moved to group {target_group_id or 'none'}")
        db.commit()
        for session in sessions:
            db.refresh(session)
            await self.publish_status(session, "updated")
        return len(sessions)

    async def move_sessions_to_agent(self, db: Session, session_ids: list[int], kf_id: int | None, owner_id: int | None = None) -> int:
        target_kf_id = None if kf_id == 0 else kf_id
        stmt = select(TelegramSession).where(TelegramSession.id.in_(session_ids))
        if owner_id is not None:
            stmt = stmt.where(TelegramSession.owner_id == owner_id)
        sessions = db.scalars(stmt).all()
        for session in sessions:
            session.kf_id = target_kf_id
            self.log(db, session.id, "move_support_agent", f"Moved to support agent {target_kf_id or 'none'}")
        db.commit()
        for session in sessions:
            db.refresh(session)
            await self.publish_status(session, "updated")
        return len(sessions)

    async def import_sessions(self, db: Session, file: UploadFile, owner_id: int | None = None) -> dict[str, int]:
        content = await file.read()
        if (file.filename or "").lower().endswith(".session"):
            created = await self._import_session_file(db, file.filename or "", content, owner_id)
            skipped = 0 if created else 1
            await session_ws_manager.broadcast("*", {"event": "bulk_imported", "created": created, "skipped": skipped})
            return {"created": created, "skipped": skipped}

        rows = self._read_import_rows(file.filename or "", content)
        created = 0
        skipped = 0
        for row in rows:
            phone = self._pick_value(row, "phone", "手机号", "手机", "账号", "session", "session号", "session_name")
            username = self._pick_value(row, "username", "用户名", "昵称", "name")
            avatar = self._pick_value(row, "avatar", "头像", "avatar_url")
            group_id = self._pick_value(row, "group_id", "分组", "分组id")
            phone = self._normalize_phone(phone)
            if not phone:
                skipped += 1
                continue
            exists_stmt = select(TelegramSession).where(TelegramSession.phone == phone)
            if owner_id is not None:
                exists_stmt = exists_stmt.where(TelegramSession.owner_id == owner_id)
            exists = db.scalar(exists_stmt)
            if exists:
                skipped += 1
                continue
            self.create_session(
                db,
                {
                    "username": username or self._make_username(phone),
                    "phone": phone,
                    "avatar": avatar or None,
                    "group_id": self._normalize_group_id(group_id),
                },
                owner_id=owner_id,
            )
            created += 1
        await session_ws_manager.broadcast("*", {"event": "bulk_imported", "created": created, "skipped": skipped})
        return {"created": created, "skipped": skipped}

    async def health_check_once(self, db: Session, owner_id: int | None = None) -> dict[str, int]:
        stmt = select(TelegramSession)
        if owner_id is not None:
            stmt = stmt.where(TelegramSession.owner_id == owner_id)
        sessions = db.scalars(stmt).all()
        checked = 0
        for session in sessions:
            checked += 1
            client = None
            try:
                client = build_client(session.session_name, proxy_service.get_proxy_url_for_session(db, session))
                await asyncio.wait_for(client.connect(), timeout=5)
                authorized = await asyncio.wait_for(client.is_user_authorized(), timeout=5)
                session.status = SessionStatus.connected if authorized else SessionStatus.disconnected
                session.health_status = "healthy" if authorized else "unauthorized"
                session.last_health_check_at = datetime.utcnow()
                session.error_message = None
                if authorized:
                    me = await asyncio.wait_for(client.get_me(), timeout=5)
                    await asyncio.wait_for(self._sync_telegram_profile(client, session, me), timeout=8)
                    session.last_login_at = datetime.utcnow()
                if client.is_connected():
                    await client.disconnect()
            except asyncio.TimeoutError:
                session.status = SessionStatus.error
                session.health_status = "unhealthy"
                session.error_message = "Telegram connection timed out"
                session.last_health_check_at = datetime.utcnow()
            except Exception as exc:
                session.status = SessionStatus.error
                session.health_status = "unhealthy"
                session.error_message = str(exc)
                session.last_health_check_at = datetime.utcnow()
            finally:
                try:
                    if client and client.is_connected():
                        await client.disconnect()
                except Exception:
                    pass
            self.log(db, session.id, "health_check", session.health_status or "unknown")
            db.commit()
            db.refresh(session)
            await self.publish_status(session, "status_changed")
        return {"checked": checked}

    def list_logs(self, db: Session, session_id: int | None = None, limit: int = 100, owner_id: int | None = None) -> list[SessionLog]:
        stmt = select(SessionLog).order_by(SessionLog.created_at.desc()).limit(limit)
        if owner_id is not None:
            stmt = stmt.join(TelegramSession, SessionLog.session_id == TelegramSession.id).where(TelegramSession.owner_id == owner_id)
        if session_id:
            stmt = stmt.where(SessionLog.session_id == session_id)
        return list(db.scalars(stmt).all())

    def count_sent_messages(self, db: Session, session_id: int) -> int:
        return db.scalar(
            select(func.count(SessionTaskLog.id)).where(SessionTaskLog.session_id == session_id, SessionTaskLog.status == "success")
        ) or 0

    def list_task_logs(self, db: Session, session_id: int, limit: int = 100) -> list[SessionTaskLog]:
        stmt = (
            select(SessionTaskLog)
            .where(SessionTaskLog.session_id == session_id)
            .order_by(SessionTaskLog.created_at.desc())
            .limit(limit)
        )
        return list(db.scalars(stmt).all())

    def log(self, db: Session, session_id: int | None, action: str, message: str) -> None:
        db.add(SessionLog(session_id=session_id, action=action, message=message))

    async def publish_status(self, session: TelegramSession, event: str) -> None:
        payload = {"event": event, "session": self.serialize_session(session)}
        await session_ws_manager.broadcast(str(session.id), payload)
        await session_ws_manager.broadcast("*", payload)

    def serialize_session(self, session: TelegramSession) -> dict[str, Any]:
        db = object_session(session)
        proxy = proxy_service.get_proxy_for_session(db, session, require_active=False) if db else None
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
            "group_color": session.group.color if session.group else None,
            "kf_id": session.kf_id,
            "kf_name": session.support_agent.name if session.support_agent else None,
            "kf_color": session.support_agent.color if session.support_agent else None,
            "proxy_id": proxy.id if proxy else None,
            "proxy_name": proxy.name if proxy else None,
            "proxy_color": proxy.color if proxy else None,
            "proxy_status": proxy.status if proxy else None,
            "sent_count": self.count_sent_messages(db, session.id) if db else 0,
            "created_at": session.created_at.isoformat() if session.created_at else None,
            "updated_at": session.updated_at.isoformat() if session.updated_at else None,
        }

    async def _sync_telegram_profile(self, client: Any, session: TelegramSession, me: Any) -> None:
        display_name = " ".join(part for part in [getattr(me, "first_name", None), getattr(me, "last_name", None)] if part)
        session.username = me.username or display_name or session.username
        session.phone = me.phone or session.phone
        avatar_path = await self._download_avatar(client, session.session_name, me)
        if avatar_path:
            session.avatar = avatar_path

    async def _download_avatar(self, client: Any, session_name: str, me: Any) -> str | None:
        avatar_dir = Path("static") / "avatars"
        avatar_dir.mkdir(parents=True, exist_ok=True)
        avatar_file = avatar_dir / f"{session_name}.jpg"
        try:
            downloaded = await client.download_profile_photo(me, file=str(avatar_file))
        except Exception:
            return None
        if not downloaded:
            return None
        return f"/static/avatars/{avatar_file.name}"

    def _make_session_name(self, phone: str) -> str:
        return "tg_" + "".join(ch for ch in phone if ch.isalnum())

    async def _import_session_file(self, db: Session, filename: str, content: bytes, owner_id: int | None = None) -> int:
        session_name = self._session_name_from_filename(filename)
        if not session_name:
            return 0
        exists_stmt = select(TelegramSession).where(TelegramSession.session_name == session_name)
        if owner_id is not None:
            exists_stmt = exists_stmt.where(TelegramSession.owner_id == owner_id)
        exists = db.scalar(exists_stmt)
        if exists:
            return 0

        session_dir = Path(settings.session_dir)
        session_dir.mkdir(parents=True, exist_ok=True)
        session_path = session_dir / f"{session_name}.session"
        session_path.write_bytes(content)

        username = session_name[:100]
        phone = self._normalize_phone(session_name) or session_name[:32]

        phone_exists_stmt = select(TelegramSession).where(TelegramSession.phone == phone)
        if owner_id is not None:
            phone_exists_stmt = phone_exists_stmt.where(TelegramSession.owner_id == owner_id)
        phone_exists = db.scalar(phone_exists_stmt)
        if phone_exists:
            session_path.unlink(missing_ok=True)
            return 0

        session = self.create_session(db, {"username": username, "phone": phone, "session_name": session_name}, owner_id=owner_id)
        session.status = SessionStatus.disconnected
        session.health_status = "unchecked"
        session.error_message = None
        session.last_health_check_at = datetime.utcnow()
        self.log(db, session.id, "import_session_file", f"Imported {filename}")
        db.commit()
        db.refresh(session)
        await self.publish_status(session, "updated")
        return 1

    def _session_name_from_filename(self, filename: str) -> str:
        stem = Path(filename).stem.strip()
        return re.sub(r"[^A-Za-z0-9_.-]+", "_", stem)[:150]

    def _read_import_rows(self, filename: str, content: bytes) -> list[dict[str, Any]]:
        suffix = Path(filename).suffix.lower()
        if suffix == ".txt":
            return self._read_plain_text_rows(content)

        if filename.lower().endswith(".csv"):
            text = content.decode("utf-8-sig")
            return self._read_csv_rows(text)

        workbook = load_workbook(io.BytesIO(content), read_only=True)
        sheet = workbook.active
        rows = list(sheet.iter_rows(values_only=True))
        if not rows:
            return []
        return self._read_tabular_rows(rows)

    def _read_csv_rows(self, text: str) -> list[dict[str, Any]]:
        sample = text[:2048]
        try:
            dialect = csv.Sniffer().sniff(sample)
        except csv.Error:
            dialect = csv.excel
        rows = list(csv.reader(io.StringIO(text), dialect))
        return self._read_tabular_rows(rows)

    def _read_plain_text_rows(self, content: bytes) -> list[dict[str, Any]]:
        text = content.decode("utf-8-sig", errors="ignore")
        rows: list[dict[str, Any]] = []
        for line in text.splitlines():
            value = line.strip()
            if not value:
                continue
            parts = re.split(r"[\s,，;；]+", value)
            if parts:
                rows.append({"phone": parts[0], "username": parts[1] if len(parts) > 1 else ""})
        return rows

    def _read_tabular_rows(self, rows: list[Any]) -> list[dict[str, Any]]:
        normalized_rows = [list(row) for row in rows if any(cell not in (None, "") for cell in row)]
        if not normalized_rows:
            return []

        first_row = [str(cell).strip() if cell is not None else "" for cell in normalized_rows[0]]
        if self._looks_like_header(first_row):
            headers = first_row
            data_rows = normalized_rows[1:]
            return [dict(zip(headers, row)) for row in data_rows]

        return [
            {
                "phone": row[0] if len(row) > 0 else "",
                "username": row[1] if len(row) > 1 else "",
                "avatar": row[2] if len(row) > 2 else "",
                "group_id": row[3] if len(row) > 3 else "",
            }
            for row in normalized_rows
        ]

    def _looks_like_header(self, row: list[str]) -> bool:
        known_headers = {
            "phone",
            "手机号",
            "手机",
            "账号",
            "session",
            "session号",
            "session_name",
            "username",
            "用户名",
            "昵称",
            "name",
            "avatar",
            "头像",
            "avatar_url",
            "group_id",
            "分组",
            "分组id",
        }
        return any(cell.lower() in known_headers for cell in row)

    def _pick_value(self, row: dict[str, Any], *keys: str) -> str:
        normalized = {str(key).strip().lower(): value for key, value in row.items()}
        for key in keys:
            value = normalized.get(key.lower())
            if value not in (None, ""):
                return str(value).strip()
        return ""

    def _normalize_phone(self, value: str) -> str:
        value = value.strip()
        if not value:
            return ""
        value = re.sub(r"\.0$", "", value)
        match = re.search(r"\+?\d[\d\s().-]{4,}\d", value)
        if not match:
            return ""
        phone = re.sub(r"[\s().-]+", "", match.group(0))
        return phone[:32]

    def _make_username(self, phone: str) -> str:
        suffix = "".join(ch for ch in phone if ch.isdigit())[-6:] or "session"
        return f"session_{suffix}"

    def _normalize_group_id(self, value: str) -> int | None:
        if not value:
            return None
        try:
            return int(float(value))
        except ValueError:
            return None


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
