import asyncio
import contextlib
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import or_, select
from telethon import events

from app.core.database import SessionLocal
from app.core.telegram import build_client
from app.models.customer import Customer
from app.models.message import Message
from app.models.session import SessionStatus, TelegramSession
from app.services.proxy_service import proxy_service


class IncomingMessageListener:
    def __init__(self) -> None:
        self._tasks: dict[int, asyncio.Task[Any]] = {}
        self._clients: dict[int, Any] = {}
        self._monitor_task: asyncio.Task[Any] | None = None
        self._stop_event = asyncio.Event()

    def start(self) -> None:
        if self._monitor_task and not self._monitor_task.done():
            return
        self._stop_event.clear()
        self._monitor_task = asyncio.create_task(self._monitor_loop())

    async def stop(self) -> None:
        self._stop_event.set()
        if self._monitor_task:
            self._monitor_task.cancel()
        for task in list(self._tasks.values()):
            task.cancel()
        for client in list(self._clients.values()):
            try:
                if client.is_connected():
                    await client.disconnect()
            except Exception:
                pass
        self._tasks.clear()
        self._clients.clear()

    async def pause_session(self, session_id: int) -> None:
        await self._stop_session(session_id)

    async def resume_session(self, session_id: int) -> None:
        db = SessionLocal()
        try:
            session = db.get(TelegramSession, session_id)
            should_listen = bool(session and session.status == SessionStatus.connected)
        finally:
            db.close()
        if should_listen and session_id not in self._tasks:
            self._tasks[session_id] = asyncio.create_task(self._listen_session(session_id))

    async def _monitor_loop(self) -> None:
        while not self._stop_event.is_set():
            await self._sync_sessions()
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=30)
            except asyncio.TimeoutError:
                pass

    async def _sync_sessions(self) -> None:
        db = SessionLocal()
        try:
            sessions = list(db.scalars(select(TelegramSession).where(TelegramSession.status == SessionStatus.connected)).all())
            active_ids = {session.id for session in sessions}
        finally:
            db.close()

        for session in sessions:
            task = self._tasks.get(session.id)
            if not task or task.done():
                self._tasks[session.id] = asyncio.create_task(self._listen_session(session.id))

        for session_id in set(self._tasks) - active_ids:
            await self._stop_session(session_id)

    async def _stop_session(self, session_id: int) -> None:
        task = self._tasks.pop(session_id, None)
        if task:
            task.cancel()
            if task is not asyncio.current_task():
                with contextlib.suppress(asyncio.CancelledError):
                    await task
        client = self._clients.pop(session_id, None)
        if client:
            try:
                if client.is_connected():
                    await client.disconnect()
            except Exception:
                pass

    async def _listen_session(self, session_id: int) -> None:
        db = SessionLocal()
        try:
            session = db.get(TelegramSession, session_id)
            if not session:
                return
            proxy_url = proxy_service.get_proxy_url_for_session(db, session)
            session_name = session.session_name
        finally:
            db.close()

        client = build_client(session_name, proxy_url)
        self._clients[session_id] = client
        try:
            await client.connect()
            if not await client.is_user_authorized():
                await self._mark_listener_error(session_id, "Session is not authorized")
                return

            @client.on(events.NewMessage(incoming=True))
            async def handler(event: Any) -> None:
                await self._store_incoming_message(session_id, event)

            await self._catch_up_recent_messages(session_id, client)
            await client.run_until_disconnected()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            await self._mark_listener_error(session_id, str(exc))
        finally:
            self._clients.pop(session_id, None)
            try:
                if client.is_connected():
                    await client.disconnect()
            except Exception:
                pass

    async def _store_incoming_message(self, session_id: int, event: Any) -> None:
        sender_id = str(event.sender_id or "")
        if not sender_id:
            return
        content = event.raw_text or "[非文本消息]"
        created_at = self._message_created_at(event)
        telegram_message_id = self._telegram_message_id(event)
        sender_name = sender_id
        try:
            sender = await event.get_sender()
            sender_access_hash = getattr(sender, "access_hash", None)
            sender_name = getattr(sender, "username", None) or " ".join(
                part for part in [getattr(sender, "first_name", None), getattr(sender, "last_name", None)] if part
            ) or sender_id
        except Exception:
            sender_access_hash = None
            pass

        db = SessionLocal()
        try:
            session = db.get(TelegramSession, session_id)
            customer = db.scalar(
                select(Customer).where(
                    Customer.owner_id == (session.owner_id if session else None),
                    Customer.assigned_session_id == session_id,
                    or_(Customer.tg_id == sender_id, Customer.phone_number == sender_id),
                )
            )
            if not customer:
                return
            customer.tg_id = customer.tg_id or sender_id
            customer.access_hash = str(sender_access_hash) if sender_access_hash else customer.access_hash
            customer.nickname = customer.nickname or sender_name
            customer.kf_id = session.kf_id if session else customer.kf_id
            customer.reply_status = "replied"
            customer.last_message_at = created_at

            chat_key = customer.tg_id or sender_id
            exists_stmt = select(Message.id).where(
                Message.session_id == session_id,
                Message.chat_id == chat_key,
                Message.direction == "inbound",
            )
            if telegram_message_id is not None:
                exists_stmt = exists_stmt.where(Message.telegram_message_id == telegram_message_id)
            else:
                exists_stmt = exists_stmt.where(
                    Message.content == content,
                    Message.created_at == created_at,
                )
            exists = db.scalar(exists_stmt)
            if exists:
                db.commit()
                return

            db.add(
                Message(
                    session_id=session_id,
                    chat_id=chat_key,
                    telegram_message_id=telegram_message_id,
                    sender=sender_name,
                    content=content,
                    direction="inbound",
                    read_status="unread",
                    created_at=created_at,
                )
            )
            db.commit()
        finally:
            db.close()

    async def _catch_up_recent_messages(self, session_id: int, client: Any) -> None:
        try:
            async for dialog in client.iter_dialogs(limit=100):
                if not getattr(dialog, "is_user", False):
                    continue
                async for message in client.iter_messages(dialog.entity, limit=20):
                    if getattr(message, "out", False):
                        continue
                    await self._store_incoming_message(session_id, message)
        except Exception as exc:
            await self._mark_listener_error(session_id, f"Catch-up failed: {exc}")

    def _message_created_at(self, event: Any) -> datetime:
        message_obj = getattr(event, "message", None)
        if not hasattr(message_obj, "date"):
            message_obj = event
        value = getattr(message_obj, "date", None)
        if not value:
            return datetime.utcnow()
        if value.tzinfo:
            return value.astimezone(timezone.utc).replace(tzinfo=None)
        return value

    def _telegram_message_id(self, event: Any) -> int | None:
        message_obj = getattr(event, "message", None)
        if not hasattr(message_obj, "id"):
            message_obj = event
        value = getattr(message_obj, "id", None)
        try:
            return int(value) if value is not None else None
        except (TypeError, ValueError):
            return None

    async def _mark_listener_error(self, session_id: int, message: str) -> None:
        db = SessionLocal()
        try:
            session = db.get(TelegramSession, session_id)
            if session:
                session.health_status = "listener_error"
                session.error_message = message[:2000]
                session.last_health_check_at = datetime.utcnow()
                db.commit()
        finally:
            db.close()


incoming_message_listener = IncomingMessageListener()
