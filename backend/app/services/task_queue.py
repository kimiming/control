import asyncio
import contextlib
import json
import random
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import distinct, select, update

from app.core.cache import redis_client
from app.core.config import get_settings
from app.core.database import SessionLocal
from app.models.session import SessionStatus, TelegramSession
from app.models.task import MarketingTask, TaskOutbox, TaskTarget
from app.services.task_service import SessionClientUnavailable, task_service
from app.services.session_service import session_service


settings = get_settings()


class TaskQueue:
    ACTIVE_TASKS_KEY = "marketing:active_tasks"
    SCHEDULED_TASKS_KEY = "marketing:scheduled_tasks"

    def __init__(self) -> None:
        self._workers: list[asyncio.Task[Any]] = []
        self._outbox_task: asyncio.Task[Any] | None = None
        self._scheduler_lock = asyncio.Lock()
        self._stopping = False

    async def start(self) -> None:
        if self._workers:
            return
        self._stopping = False
        await redis_client.ping()
        if settings.session_worker_index == 0:
            recovery_token = uuid.uuid4().hex
            if await redis_client.set("marketing:queue:recovery_lock", recovery_token, nx=True, ex=120):
                try:
                    if not await redis_client.exists("marketing:queue:ready"):
                        await self._recover_jobs()
                    await redis_client.set("marketing:queue:ready", "1")
                finally:
                    await self._release_lock("marketing:queue:recovery_lock", recovery_token)
        else:
            for _ in range(60):
                if await redis_client.exists("marketing:queue:ready"):
                    break
                await asyncio.sleep(1)
        concurrency = max(1, settings.task_global_concurrency)
        self._workers = [asyncio.create_task(self._worker(index)) for index in range(concurrency)]
        self._outbox_task = asyncio.create_task(self._outbox_loop())

    async def stop(self) -> None:
        self._stopping = True
        for worker in self._workers:
            worker.cancel()
        if self._outbox_task:
            self._outbox_task.cancel()
        for worker in self._workers:
            with contextlib.suppress(asyncio.CancelledError):
                await worker
        self._workers.clear()
        if self._outbox_task:
            with contextlib.suppress(asyncio.CancelledError):
                await self._outbox_task
        self._outbox_task = None

    async def enqueue_task(self, db: Any, task_id: int, owner_id: int | None) -> MarketingTask:
        enqueue_key = f"marketing:task_enqueue_lock:{task_id}"
        token = uuid.uuid4().hex
        if not await redis_client.set(enqueue_key, token, nx=True, ex=30):
            raise ValueError("Task is already being queued")
        try:
            online_session_ids: set[int] = set()
            async for key in redis_client.scan_iter(match="telegram:session:runtime:*"):
                try:
                    online_session_ids.add(int(str(key).rsplit(":", 1)[-1]))
                except ValueError:
                    continue
            task, _ = task_service.prepare_queued_task(db, task_id, owner_id, online_session_ids)
            await self.publish_pending_outbox(task.id)
            return task
        finally:
            await self._release_lock(enqueue_key, token)

    def _jobs_key(self, task_id: int) -> str:
        return f"marketing:task:{task_id}:jobs"

    def _pending_sessions_key(self, task_id: int) -> str:
        return f"marketing:task:{task_id}:pending_sessions"

    def _auto_woken_key(self, task_id: int) -> str:
        return f"marketing:task:{task_id}:auto_woken"

    def _active_sessions_key(self, task_id: int) -> str:
        return f"marketing:task:{task_id}:active_sessions"

    async def _connect_for_task(self, task_id: int, session_id: int) -> bool:
        runtime_key = f"telegram:session:runtime:{session_id}"
        if await redis_client.exists(runtime_key):
            return True
        db = SessionLocal()
        try:
            session = db.get(TelegramSession, session_id)
            if not session:
                return False
            result = await session_service.connect_session(db, session)
            if result.status != SessionStatus.connected or not await redis_client.exists(runtime_key):
                return False
            await redis_client.sadd(self._auto_woken_key(task_id), session_id)
            return True
        finally:
            db.close()

    def _replace_unavailable_session(self, task_id: int, session_id: int) -> int | None:
        db = SessionLocal()
        try:
            task = db.get(MarketingTask, task_id)
            if not task:
                return None
            assigned_ids = select(TaskTarget.session_id).where(
                TaskTarget.task_id == task_id,
                TaskTarget.session_id.is_not(None),
            )
            stmt = select(TelegramSession.id).where(
                TelegramSession.owner_id == task.owner_id,
                TelegramSession.id.not_in(assigned_ids),
            )
            if task.session_group_id:
                stmt = stmt.where(TelegramSession.group_id == task.session_group_id)
            replacement_id = db.scalar(stmt.order_by(TelegramSession.created_at.asc(), TelegramSession.id.asc()).limit(1))
            if replacement_id is None:
                db.execute(update(TaskTarget).where(
                    TaskTarget.task_id == task_id,
                    TaskTarget.session_id == session_id,
                    TaskTarget.status == "queued",
                ).values(status="unassigned", error_message="Session无法连接且没有可用候补账号"))
                db.commit()
                return None
            db.execute(update(TaskTarget).where(
                TaskTarget.task_id == task_id,
                TaskTarget.session_id == session_id,
                TaskTarget.status == "queued",
            ).values(session_id=int(replacement_id), error_message=None))
            db.commit()
            return int(replacement_id)
        finally:
            db.close()

    async def _activate_session_window(self, task_id: int) -> None:
        jobs_key = self._jobs_key(task_id)
        pending_key = self._pending_sessions_key(task_id)
        active_count = int(await redis_client.scard(self._active_sessions_key(task_id)))
        slots = max(settings.task_session_window - active_count, 0)
        while slots > 0:
            candidates: list[int] = []
            for _ in range(slots):
                raw_session_id = await redis_client.lpop(pending_key)
                if raw_session_id is None:
                    break
                candidates.append(int(raw_session_id))
            if not candidates:
                break
            results = await asyncio.gather(
                *[self._connect_for_task(task_id, session_id) for session_id in candidates],
                return_exceptions=True,
            )
            connected = [
                session_id for session_id, result in zip(candidates, results)
                if result is True
            ]
            failed = [
                session_id for session_id, result in zip(candidates, results)
                if result is not True
            ]
            replacements = [self._replace_unavailable_session(task_id, session_id) for session_id in failed]
            replacements = [session_id for session_id in replacements if session_id is not None]
            if replacements:
                await redis_client.rpush(pending_key, *replacements)
            if connected:
                await redis_client.sadd(self._active_sessions_key(task_id), *connected)
                await redis_client.rpush(jobs_key, *[
                    json.dumps({"task_id": task_id, "session_id": session_id})
                    for session_id in connected
                ])
                slots -= len(connected)
        if await redis_client.llen(jobs_key) and await redis_client.sadd(self.SCHEDULED_TASKS_KEY, task_id):
            await redis_client.rpush(self.ACTIVE_TASKS_KEY, task_id)

    async def _retire_task_session(self, task_id: int, session_id: int) -> None:
        await redis_client.srem(self._active_sessions_key(task_id), session_id)
        if await redis_client.sismember(self._auto_woken_key(task_id), session_id):
            db = SessionLocal()
            try:
                session = db.get(TelegramSession, session_id)
                if session:
                    await session_service.disconnect_session(db, session)
            except Exception:
                pass
            finally:
                db.close()
            await redis_client.srem(self._auto_woken_key(task_id), session_id)
        await self._activate_session_window(task_id)

    async def _schedule_task(self, task_id: int, session_ids: list[int], replace: bool = False) -> None:
        jobs_key = self._jobs_key(task_id)
        if replace:
            await redis_client.delete(
                jobs_key,
                self._pending_sessions_key(task_id),
                self._active_sessions_key(task_id),
            )
        if session_ids:
            await redis_client.rpush(self._pending_sessions_key(task_id), *session_ids)
            await self._activate_session_window(task_id)

    async def _recover_jobs(self) -> None:
        await redis_client.delete(self.ACTIVE_TASKS_KEY, self.SCHEDULED_TASKS_KEY)
        async for key in redis_client.scan_iter(match="marketing:task:*:jobs"):
            await redis_client.delete(key)

        db = SessionLocal()
        try:
            tasks = list(db.scalars(select(MarketingTask).where(MarketingTask.status.in_(["queued", "running"]))).all())
            for task in tasks:
                processing = list(db.scalars(select(TaskTarget).where(
                    TaskTarget.task_id == task.id,
                    TaskTarget.status == "processing",
                )).all())
                for target in processing:
                    target.status = "uncertain"
                    target.error_message = "服务中断时正在发送，为避免重复发送未自动重试"
                task.status = "queued"
            db.commit()

            for task in tasks:
                session_ids = list(db.scalars(select(distinct(TaskTarget.session_id)).where(
                    TaskTarget.task_id == task.id,
                    TaskTarget.status == "queued",
                    TaskTarget.session_id.is_not(None),
                )).all())
                if session_ids:
                    await self._schedule_task(task.id, [int(value) for value in session_ids], replace=True)
                else:
                    await task_service._finish_background_task(db, task)
            pending = list(db.scalars(select(TaskOutbox).where(TaskOutbox.status == "pending")).all())
            for event in pending:
                event.status = "published"
                event.published_at = datetime.utcnow()
            db.commit()
        finally:
            db.close()

    async def pause_task(self, task_id: int) -> None:
        async with self._scheduler_lock:
            await redis_client.lrem(self.ACTIVE_TASKS_KEY, 0, task_id)
            await redis_client.srem(self.SCHEDULED_TASKS_KEY, task_id)
            await redis_client.delete(self._jobs_key(task_id))

    async def cancel_task(self, task_id: int) -> None:
        await self.pause_task(task_id)

    async def publish_pending_outbox(self, task_id: int | None = None) -> int:
        publish_key = "marketing:outbox_publish_lock"
        token = uuid.uuid4().hex
        if not await redis_client.set(publish_key, token, nx=True, ex=30):
            return 0
        db = SessionLocal()
        published = 0
        try:
            stmt = select(TaskOutbox).where(TaskOutbox.status == "pending").order_by(TaskOutbox.id.asc()).limit(100)
            if task_id is not None:
                stmt = stmt.where(TaskOutbox.task_id == task_id)
            events = list(db.scalars(stmt).all())
            for event in events:
                event.attempts += 1
                try:
                    payload = json.loads(event.payload_json)
                    await self._schedule_task(int(payload["task_id"]), [int(value) for value in payload.get("session_ids", [])], replace=True)
                    event.status = "published"
                    event.published_at = datetime.utcnow()
                    event.last_error = None
                    published += 1
                except Exception as exc:
                    event.last_error = str(exc)[:2000]
                db.commit()
            return published
        finally:
            db.close()
            await self._release_lock(publish_key, token)

    async def _outbox_loop(self) -> None:
        while not self._stopping:
            try:
                await self.publish_pending_outbox()
            except Exception:
                pass
            await asyncio.sleep(1)

    async def _next_job(self) -> dict[str, int] | None:
        async with self._scheduler_lock:
            task_id = await redis_client.lpop(self.ACTIVE_TASKS_KEY)
            if task_id is None:
                return None
            jobs_key = self._jobs_key(int(task_id))
            raw_job = await redis_client.lpop(jobs_key)
            if await redis_client.llen(jobs_key):
                await redis_client.rpush(self.ACTIVE_TASKS_KEY, task_id)
            else:
                await redis_client.srem(self.SCHEDULED_TASKS_KEY, task_id)
            if not raw_job:
                return None
            payload = json.loads(raw_job)
            return {"task_id": int(payload["task_id"]), "session_id": int(payload["session_id"])}

    async def _requeue_job(self, job: dict[str, int]) -> None:
        task_id = job["task_id"]
        await redis_client.rpush(self._jobs_key(task_id), json.dumps(job))
        if await redis_client.sadd(self.SCHEDULED_TASKS_KEY, task_id):
            await redis_client.rpush(self.ACTIVE_TASKS_KEY, task_id)

    async def _worker(self, worker_index: int) -> None:
        while not self._stopping:
            job = await self._next_job()
            if not job:
                await asyncio.sleep(0.5)
                continue
            from app.services.incoming_listener import incoming_message_listener
            if not incoming_message_listener.owns_shard(job["session_id"]):
                await self._requeue_job(job)
                await asyncio.sleep(0.1)
                continue
            lock_key = f"marketing:session_lock:{job['session_id']}"
            lock_token = f"{worker_index}:{uuid.uuid4().hex}"
            acquired = await redis_client.set(lock_key, lock_token, nx=True, ex=max(settings.task_session_lock_seconds, 30))
            if not acquired:
                await self._requeue_job(job)
                await asyncio.sleep(1)
                continue
            renewer = asyncio.create_task(self._renew_lock(lock_key, lock_token))
            retry_unavailable = False
            session_finished = False
            try:
                try:
                    cooldown_seconds = await task_service.process_session_job(job["task_id"], job["session_id"])
                    db = SessionLocal()
                    try:
                        task_row = db.get(MarketingTask, job["task_id"])
                        has_more = bool(db.scalar(select(TaskTarget.id).where(
                            TaskTarget.task_id == job["task_id"],
                            TaskTarget.session_id == job["session_id"],
                            TaskTarget.status == "queued",
                        ).limit(1)))
                        task_is_active = bool(task_row and task_row.status in {"queued", "running"})
                        session_finished = not has_more
                        task_delay_min = task_row.send_interval_min if task_row else 0
                        task_delay_max = task_row.send_interval_max if task_row else 0
                    finally:
                        db.close()
                    if has_more and task_is_active:
                        if cooldown_seconds:
                            asyncio.create_task(self._requeue_after(job, cooldown_seconds))
                        else:
                            await asyncio.sleep(random.uniform(task_delay_min or 0, task_delay_max or 0))
                            await self._requeue_job(job)
                except SessionClientUnavailable:
                    await self._requeue_job(job)
                    retry_unavailable = True
            finally:
                renewer.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await renewer
                await self._release_lock(lock_key, lock_token)
            if session_finished:
                await self._retire_task_session(job["task_id"], job["session_id"])
            if retry_unavailable:
                await asyncio.sleep(5)

    async def _requeue_after(self, job: dict[str, int], delay_seconds: int) -> None:
        await asyncio.sleep(max(delay_seconds, 1))
        db = SessionLocal()
        try:
            task = db.get(MarketingTask, job["task_id"])
            has_more = bool(db.scalar(select(TaskTarget.id).where(
                TaskTarget.task_id == job["task_id"],
                TaskTarget.session_id == job["session_id"],
                TaskTarget.status == "queued",
            ).limit(1)))
            if task and task.status in {"queued", "running"} and has_more:
                await self._requeue_job(job)
        finally:
            db.close()

    async def _renew_lock(self, key: str, token: str) -> None:
        interval = max(settings.task_session_lock_seconds // 3, 10)
        while True:
            await asyncio.sleep(interval)
            await redis_client.eval(
                "if redis.call('get', KEYS[1]) == ARGV[1] then return redis.call('expire', KEYS[1], ARGV[2]) else return 0 end",
                1,
                key,
                token,
                max(settings.task_session_lock_seconds, 30),
            )

    async def _release_lock(self, key: str, token: str) -> None:
        await redis_client.eval(
            "if redis.call('get', KEYS[1]) == ARGV[1] then return redis.call('del', KEYS[1]) else return 0 end",
            1,
            key,
            token,
        )


task_queue = TaskQueue()
