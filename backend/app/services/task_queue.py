import asyncio
import contextlib
import json
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import distinct, select

from app.core.cache import redis_client
from app.core.config import get_settings
from app.core.database import SessionLocal
from app.models.task import MarketingTask, TaskOutbox, TaskTarget
from app.services.task_service import task_service


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
        await self._recover_jobs()
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
            task, _ = task_service.prepare_queued_task(db, task_id, owner_id)
            await self.publish_pending_outbox(task.id)
            return task
        finally:
            await self._release_lock(enqueue_key, token)

    def _jobs_key(self, task_id: int) -> str:
        return f"marketing:task:{task_id}:jobs"

    async def _schedule_task(self, task_id: int, session_ids: list[int], replace: bool = False) -> None:
        jobs_key = self._jobs_key(task_id)
        if replace:
            await redis_client.delete(jobs_key)
        if session_ids:
            await redis_client.rpush(jobs_key, *[json.dumps({"task_id": task_id, "session_id": sid}) for sid in session_ids])
            if await redis_client.sadd(self.SCHEDULED_TASKS_KEY, task_id):
                await redis_client.rpush(self.ACTIVE_TASKS_KEY, task_id)

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
                    await self._schedule_task(task.id, [int(value) for value in session_ids])
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
            lock_key = f"marketing:session_lock:{job['session_id']}"
            lock_token = f"{worker_index}:{uuid.uuid4().hex}"
            acquired = await redis_client.set(lock_key, lock_token, nx=True, ex=max(settings.task_session_lock_seconds, 30))
            if not acquired:
                await self._requeue_job(job)
                await asyncio.sleep(1)
                continue
            renewer = asyncio.create_task(self._renew_lock(lock_key, lock_token))
            try:
                await task_service.process_session_job(job["task_id"], job["session_id"])
            finally:
                renewer.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await renewer
                await self._release_lock(lock_key, lock_token)

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
