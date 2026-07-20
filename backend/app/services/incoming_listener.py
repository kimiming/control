import asyncio
import contextlib
import json
import random
import time
import uuid
from pathlib import Path
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import or_, select, update
from telethon import events
from telethon import utils as telethon_utils
from telethon.tl.functions.contacts import DeleteContactsRequest, GetContactsRequest, ImportContactsRequest
from telethon.tl.types import InputMediaContact, InputPeerUser, InputPhoneContact
from redis.exceptions import ResponseError

from app.core.config import get_settings
from app.core.cache import redis_client
from app.core.database import SessionLocal
from app.core.telegram import build_client
from app.models.customer import Customer
from app.models.message import Message
from app.models.session import SessionStatus, TelegramSession
from app.services.proxy_service import proxy_service
from app.services.target_parser import normalize_username
from app.services.session_command_bus import session_command_bus

settings = get_settings()


class IncomingMessageListener:
    def __init__(self) -> None:
        self._tasks: dict[int, asyncio.Task[Any]] = {}
        self._clients: dict[int, Any] = {}
        self._paused_ids: set[int] = set()
        self._operation_locks: dict[int, asyncio.Lock] = defaultdict(asyncio.Lock)
        self._failure_counts: dict[int, int] = defaultdict(int)
        self._retry_after: dict[int, float] = {}
        self._connect_semaphore = asyncio.Semaphore(max(settings.session_connect_concurrency, 1))
        self._monitor_task: asyncio.Task[Any] | None = None
        self._inbound_tasks: list[asyncio.Task[Any]] = []
        self._command_tasks: list[asyncio.Task[Any]] = []
        self._stop_event = asyncio.Event()

    def start(self) -> None:
        if self._monitor_task and not self._monitor_task.done():
            return
        self._stop_event.clear()
        self._monitor_task = asyncio.create_task(self._monitor_loop())
        self._inbound_tasks = [
            asyncio.create_task(self._inbound_consumer(index))
            for index in range(max(settings.inbound_db_workers, 1))
        ]
        self._command_tasks = [asyncio.create_task(self._command_consumer()) for _ in range(max(settings.session_command_workers, 1))]

    async def stop(self) -> None:
        self._stop_event.set()
        if self._monitor_task:
            self._monitor_task.cancel()
        for task in list(self._tasks.values()):
            task.cancel()
        for task in self._inbound_tasks:
            task.cancel()
        for task in self._command_tasks:
            task.cancel()
        for client in list(self._clients.values()):
            try:
                if client.is_connected():
                    await client.disconnect()
            except Exception:
                pass
        self._tasks.clear()
        self._clients.clear()
        for task in self._inbound_tasks:
            with contextlib.suppress(asyncio.CancelledError):
                await task
        self._inbound_tasks.clear()
        for task in self._command_tasks:
            with contextlib.suppress(asyncio.CancelledError):
                await task
        self._command_tasks.clear()

    async def pause_session(self, session_id: int) -> None:
        self._paused_ids.add(session_id)
        await self._stop_session(session_id)

    async def resume_session(self, session_id: int) -> None:
        self._paused_ids.discard(session_id)
        db = SessionLocal()
        try:
            session = db.get(TelegramSession, session_id)
            should_listen = bool(session and session.status == SessionStatus.connected)
        finally:
            db.close()
        if should_listen and session_id not in self._tasks:
            self._tasks[session_id] = asyncio.create_task(self._listen_session(session_id))

    def get_connected_client(self, session_id: int) -> Any | None:
        """Return the listener-owned client so send jobs can reuse one SQLite session connection."""
        client = self._clients.get(session_id)
        if client and client.is_connected():
            return client
        return None

    async def wait_for_connected_client(self, session_id: int) -> Any | None:
        deadline = asyncio.get_running_loop().time() + max(settings.session_client_wait_seconds, 0)
        while True:
            client = self.get_connected_client(session_id)
            if client is not None:
                return client
            if asyncio.get_running_loop().time() >= deadline:
                return None
            await asyncio.sleep(0.5)

    def owns_shard(self, session_id: int) -> bool:
        worker_count = max(settings.session_worker_count, 1)
        worker_index = settings.session_worker_index % worker_count
        return session_id % worker_count == worker_index

    async def acquire_client_operation(self, session_id: int) -> None:
        await self._operation_locks[session_id].acquire()

    def release_client_operation(self, session_id: int) -> None:
        lock = self._operation_locks.get(session_id)
        if lock and lock.locked():
            lock.release()

    async def _monitor_loop(self) -> None:
        while not self._stop_event.is_set():
            await self._sync_sessions()
            await self._publish_runtime_states()
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=30)
            except asyncio.TimeoutError:
                pass

    async def _publish_runtime_states(self) -> None:
        for session_id, client in list(self._clients.items()):
            if not client.is_connected():
                continue
            await self._publish_runtime_state(session_id)

    async def _publish_runtime_state(self, session_id: int) -> None:
        key = f"telegram:session:runtime:{session_id}"
        await redis_client.set(key, json.dumps({
                "status": "online", "worker": settings.session_worker_index,
                "last_heartbeat": datetime.utcnow().isoformat(),
        }), ex=max(settings.session_runtime_ttl_seconds, 30))

    async def _sync_sessions(self) -> None:
        db = SessionLocal()
        try:
            sessions = list(db.scalars(
                select(TelegramSession)
                .where(TelegramSession.status == SessionStatus.connected)
                .where(TelegramSession.id % max(settings.session_worker_count, 1) == settings.session_worker_index % max(settings.session_worker_count, 1))
                .order_by(TelegramSession.last_login_at.desc(), TelegramSession.id.asc())
            ).all())
        finally:
            db.close()

        active_ids = {session.id for session in sessions}

        for session in sessions:
            if session.id in self._paused_ids:
                continue
            task = self._tasks.get(session.id)
            if not task or task.done():
                if time.monotonic() < self._retry_after.get(session.id, 0):
                    continue
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
        await redis_client.delete(f"telegram:session:runtime:{session_id}")

    async def _listen_session(self, session_id: int) -> None:
        if not self.owns_shard(session_id):
            return
        owner_key = f"telegram:session:owner:{session_id}"
        owner_token = f"{settings.session_worker_index}:{uuid.uuid4().hex}"
        lock_seconds = max(settings.session_owner_lock_seconds, 30)
        db = SessionLocal()
        try:
            session = db.get(TelegramSession, session_id)
            if not session:
                return
            proxy_url = proxy_service.get_proxy_url_for_session(db, session)
            session_name = session.session_name
        finally:
            db.close()

        if not await redis_client.set(owner_key, owner_token, nx=True, ex=lock_seconds):
            return
        renewer = asyncio.create_task(self._renew_owner_lock(owner_key, owner_token, lock_seconds))
        client = build_client(session_name, proxy_url)
        connected_at: float | None = None
        cancelled = False
        try:
            async with self._connect_semaphore:
                await asyncio.wait_for(client.connect(), timeout=20)
                authorized = await asyncio.wait_for(client.is_user_authorized(), timeout=20)
            if not authorized:
                await self._mark_listener_error(session_id, "Session is not authorized")
                return

            @client.on(events.NewMessage(incoming=True))
            async def handler(event: Any) -> None:
                await self._store_incoming_message(session_id, event)

            @client.on(events.MessageRead)
            async def read_handler(event: Any) -> None:
                await self._store_outbound_read_receipt(session_id, event)

            # Publish the client only after Telethon has fully connected,
            # authorized and installed its event handlers. Send workers must not
            # race client.connect() by observing a half-initialized transport.
            self._clients[session_id] = client
            await self._publish_runtime_state(session_id)
            await self._mark_listener_online(session_id)
            connected_at = time.monotonic()
            if settings.session_startup_history_sync:
                await self._catch_up_recent_messages(session_id, client)
            await client.run_until_disconnected()
        except asyncio.CancelledError:
            cancelled = True
            raise
        except Exception as exc:
            await self._mark_listener_error(session_id, str(exc))
        finally:
            self._clients.pop(session_id, None)
            await redis_client.delete(f"telegram:session:runtime:{session_id}")
            try:
                if client.is_connected():
                    await client.disconnect()
            except Exception:
                pass
            renewer.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await renewer
            await self._release_owner_lock(owner_key, owner_token)
            if not cancelled:
                online_seconds = time.monotonic() - connected_at if connected_at is not None else 0
                if online_seconds >= 300:
                    self._failure_counts[session_id] = 0
                self._failure_counts[session_id] += 1
                base = min(5 * (2 ** min(self._failure_counts[session_id] - 1, 8)), 900)
                self._retry_after[session_id] = time.monotonic() + base * random.uniform(0.8, 1.2)

    async def _renew_owner_lock(self, key: str, token: str, lock_seconds: int) -> None:
        while True:
            await asyncio.sleep(max(lock_seconds // 3, 10))
            renewed = await redis_client.eval(
                "if redis.call('get', KEYS[1]) == ARGV[1] then return redis.call('expire', KEYS[1], ARGV[2]) else return 0 end",
                1, key, token, lock_seconds,
            )
            if not renewed:
                return

    async def _release_owner_lock(self, key: str, token: str) -> None:
        await redis_client.eval(
            "if redis.call('get', KEYS[1]) == ARGV[1] then return redis.call('del', KEYS[1]) else return 0 end",
            1, key, token,
        )

    async def _command_consumer(self) -> None:
        queue_key = f"telegram:worker:{settings.session_worker_index}:commands"
        while not self._stop_event.is_set():
            item = await redis_client.blpop(queue_key, timeout=5)
            if not item:
                continue
            command = json.loads(item[1])
            response_key = str(command["response_key"])
            try:
                result = await self._execute_command(
                    int(command["session_id"]), str(command["command"]), dict(command.get("payload") or {})
                )
                await session_command_bus.respond(response_key, {"ok": True, "result": result})
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                await session_command_bus.respond(response_key, {"ok": False, "error": str(exc)[:2000]})

    async def _execute_command(self, session_id: int, command: str, payload: dict[str, Any]) -> dict[str, Any]:
        if not self.owns_shard(session_id):
            raise RuntimeError("Session不属于当前Worker分片")
        if command == "disconnect":
            await self.pause_session(session_id)
            return {"status": "offline"}
        if command == "connect":
            await self.resume_session(session_id)
        await self.acquire_client_operation(session_id)
        try:
            client = await self.wait_for_connected_client(session_id)
            if client is None:
                raise RuntimeError("Session当前未真实在线")
            if command in {"connect", "health"}:
                if not await client.is_user_authorized():
                    raise RuntimeError("Session未授权")
                me = await client.get_me()
                return {"status": "online", "telegram_id": str(me.id), "username": getattr(me, "username", None)}
            if command == "contacts_scan":
                result = await client(GetContactsRequest(hash=0))
                return {"contact_count": len(getattr(result, "users", []) or [])}
            if command == "contacts_clear":
                result = await client(GetContactsRequest(hash=0))
                users = getattr(result, "users", []) or []
                input_users = [telethon_utils.get_input_user(user) for user in users]
                for offset in range(0, len(input_users), 100):
                    await client(DeleteContactsRequest(id=input_users[offset:offset + 100]))
                return {"deleted": len(input_users), "contact_count": 0}
            if command == "contacts_import":
                phones = [str(value) for value in payload.get("phones", [])]
                for offset in range(0, len(phones), 500):
                    batch = [InputPhoneContact(client_id=offset+i+1, phone=phone, first_name=phone, last_name="") for i, phone in enumerate(phones[offset:offset+500])]
                    await client(ImportContactsRequest(batch))
                result = await client(GetContactsRequest(hash=0))
                return {"imported": len(phones), "contact_count": len(getattr(result, "users", []) or [])}
            if command in {"reply", "ack_read"}:
                entity: Any
                if payload.get("tg_id") and payload.get("access_hash"):
                    entity = InputPeerUser(int(payload["tg_id"]), int(payload["access_hash"]))
                else:
                    entity = payload.get("username") or payload.get("phone_number") or payload.get("tg_id")
                if not entity:
                    raise RuntimeError("客户缺少可用的Telegram标识")
                entity = await client.get_input_entity(entity)
                if command == "ack_read":
                    await client.send_read_acknowledge(entity)
                    return {"acknowledged": True}
                material = dict(payload.get("material") or {})
                text = str(payload.get("text") or "")
                material_type = material.get("material_type")
                image_path = None
                if material_type == "image":
                    image_path = material.get("file_path")
                    local_path = Path(str(image_path))
                    if not local_path.is_absolute():
                        local_path = Path("/app") / str(image_path).lstrip("/")
                    sent = await client.send_file(entity, str(local_path), caption=text)
                    content = text or f"图片素材：{material.get('name') or '-'}"
                elif material_type == "contact":
                    card = dict(material.get("contact_card") or {})
                    sent = await client.send_file(entity, InputMediaContact(
                        phone_number=str(card.get("phone_number") or ""),
                        first_name=str(card.get("first_name") or ""),
                        last_name=str(card.get("last_name") or ""),
                        vcard=str(card.get("vcard") or ""),
                    ))
                    content = text or f"名片：{card.get('first_name') or '-'}"
                else:
                    content = str(material.get("content") or text).strip()
                    if not content:
                        raise RuntimeError("回复内容为空")
                    sent = await client.send_message(entity, content)
                return {"content": content, "image_path": image_path, "telegram_message_id": getattr(sent, "id", None)}
            if command == "bidirectional_check":
                sent = await client.send_message("@SpamBot", "/start")
                await asyncio.sleep(2)
                response = ""
                async for message in client.iter_messages("@SpamBot", limit=5):
                    if not getattr(message, "out", False) and getattr(message, "id", 0) > getattr(sent, "id", 0):
                        response = str(getattr(message, "raw_text", "") or "")
                        break
                return {"response": response}
            raise RuntimeError(f"不支持的Session命令: {command}")
        finally:
            self.release_client_operation(session_id)

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
            sender_username = normalize_username(getattr(sender, "username", None))
            sender_phone = getattr(sender, "phone", None)
            if sender_phone and not str(sender_phone).startswith("+"):
                sender_phone = f"+{sender_phone}"
            sender_name = getattr(sender, "username", None) or " ".join(
                part for part in [getattr(sender, "first_name", None), getattr(sender, "last_name", None)] if part
            ) or sender_id
        except Exception:
            sender_access_hash = None
            sender_username = None
            sender_phone = None
            pass

        payload = {
            "session_id": session_id,
            "sender_id": sender_id,
            "sender_name": sender_name,
            "sender_access_hash": str(sender_access_hash) if sender_access_hash else None,
            "sender_username": sender_username,
            "sender_phone": str(sender_phone) if sender_phone else None,
            "content": content,
            "created_at": created_at.isoformat(),
            "enqueued_at": datetime.utcnow().isoformat(),
            "telegram_message_id": telegram_message_id,
        }
        try:
            await redis_client.xadd(
                settings.inbound_stream_name,
                {"payload": json.dumps(payload, ensure_ascii=False)},
                maxlen=max(settings.inbound_stream_maxlen, 1000),
                approximate=True,
            )
        except Exception:
            await asyncio.to_thread(self._persist_incoming_payload, payload)

    def _persist_incoming_payload(self, payload: dict[str, Any]) -> None:
        session_id = int(payload["session_id"])
        sender_id = str(payload["sender_id"])
        sender_name = str(payload.get("sender_name") or sender_id)
        sender_access_hash = payload.get("sender_access_hash")
        sender_username = payload.get("sender_username")
        sender_phone = payload.get("sender_phone")
        content = str(payload.get("content") or "[非文本消息]")
        created_at = datetime.fromisoformat(str(payload["created_at"]))
        telegram_message_id = payload.get("telegram_message_id")

        db = SessionLocal()
        try:
            session = db.get(TelegramSession, session_id)
            customer_identifiers = [Customer.tg_id == sender_id, Customer.phone_number == sender_id]
            if sender_username:
                customer_identifiers.append(Customer.username == sender_username)
            customer = db.scalar(
                select(Customer).where(
                    Customer.owner_id == (session.owner_id if session else None),
                    Customer.assigned_session_id == session_id,
                    or_(*customer_identifiers),
                )
            )
            if not customer:
                enqueued_at = datetime.fromisoformat(str(payload.get("enqueued_at") or payload["created_at"]))
                if (datetime.utcnow() - enqueued_at).total_seconds() < 300:
                    raise RuntimeError("Customer record is not available yet")
                return
            customer.tg_id = customer.tg_id or sender_id
            customer.access_hash = str(sender_access_hash) if sender_access_hash else customer.access_hash
            customer.username = sender_username or customer.username
            customer.phone_number = str(sender_phone) if sender_phone else customer.phone_number
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

    async def _ensure_inbound_group(self) -> None:
        try:
            await redis_client.xgroup_create(
                settings.inbound_stream_name,
                settings.inbound_stream_group,
                id="0-0",
                mkstream=True,
            )
        except ResponseError as exc:
            if "BUSYGROUP" not in str(exc):
                raise

    async def _inbound_consumer(self, index: int) -> None:
        while not self._stop_event.is_set():
            try:
                await self._ensure_inbound_group()
                break
            except asyncio.CancelledError:
                raise
            except Exception:
                await asyncio.sleep(5)
        consumer = f"worker-{settings.session_worker_index}-{index}-{uuid.uuid4().hex[:8]}"
        last_claim = 0.0
        while not self._stop_event.is_set():
            entries: list[tuple[str, dict[str, str]]] = []
            now = asyncio.get_running_loop().time()
            if index == 0 and now - last_claim >= 30:
                last_claim = now
                try:
                    claimed = await redis_client.xautoclaim(
                        settings.inbound_stream_name,
                        settings.inbound_stream_group,
                        consumer,
                        min_idle_time=60000,
                        start_id="0-0",
                        count=20,
                    )
                    if len(claimed) >= 2:
                        entries.extend(claimed[1])
                except asyncio.CancelledError:
                    raise
                except Exception:
                    await asyncio.sleep(1)
            if not entries:
                try:
                    response = await redis_client.xreadgroup(
                        settings.inbound_stream_group,
                        consumer,
                        {settings.inbound_stream_name: ">"},
                        count=20,
                        block=5000,
                    )
                except asyncio.CancelledError:
                    raise
                except Exception:
                    await asyncio.sleep(2)
                    continue
                if response:
                    entries.extend(response[0][1])
            for entry_id, fields in entries:
                try:
                    payload = json.loads(fields["payload"])
                    await asyncio.to_thread(self._persist_incoming_payload, payload)
                except asyncio.CancelledError:
                    raise
                except Exception:
                    continue
                await redis_client.xack(
                    settings.inbound_stream_name,
                    settings.inbound_stream_group,
                    entry_id,
                )

    async def _store_outbound_read_receipt(self, session_id: int, event: Any) -> None:
        max_id = getattr(event, "max_id", None)
        chat_id = getattr(event, "chat_id", None)
        if not max_id or chat_id is None:
            return
        chat_key = str(chat_id)
        db = SessionLocal()
        try:
            customer = db.scalar(
                select(Customer).where(
                    Customer.assigned_session_id == session_id,
                    Customer.tg_id == chat_key,
                )
            )
            chat_keys = [chat_key]
            if customer:
                chat_keys.extend(value for value in [customer.tg_id, customer.username, customer.phone_number] if value)
            db.execute(
                update(Message)
                .where(
                    Message.session_id == session_id,
                    Message.chat_id.in_(set(chat_keys)),
                    Message.direction == "outbound",
                    Message.telegram_message_id.is_not(None),
                    Message.telegram_message_id <= int(max_id),
                    Message.read_status != "read",
                )
                .values(read_status="read")
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

    async def _mark_listener_online(self, session_id: int) -> None:
        db = SessionLocal()
        try:
            session = db.get(TelegramSession, session_id)
            if session:
                session.status = SessionStatus.connected
                session.health_status = "healthy"
                session.error_message = None
                session.last_health_check_at = datetime.utcnow()
                db.commit()
        finally:
            db.close()


incoming_message_listener = IncomingMessageListener()
