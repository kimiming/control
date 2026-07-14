import asyncio
import json
import random
import re
from datetime import datetime, timedelta
from typing import Any

from fastapi import UploadFile
from sqlalchemy import case, delete, func, insert, or_, select, update
from sqlalchemy.orm import Session
from telethon.tl.functions.messages import SendMediaRequest
from telethon.tl.functions.contacts import GetContactsRequest, ImportContactsRequest
from telethon.tl.types import InputMediaContact, InputPeerUser, InputPhoneContact

from app.core.telegram import build_client
from app.models.customer import Customer
from app.models.customer_profile import CustomerProfile
from app.models.session import SessionStatus, SessionTaskLog, TelegramSession
from app.models.task import MarketingTask, TaskOutbox, TaskTarget
from app.models.message import Message
from app.models.material import Material
from app.models.proxy import ProxyConfig
from app.services.customer_service import customer_service
from app.services.image_storage import save_compressed_image
from app.services.material_service import material_service
from app.services.proxy_service import proxy_service
from app.services.target_parser import normalize_username, parse_targets, validate_target_type


class TaskService:
    def list_tasks(self, db: Session, owner_id: int | None = None) -> list[MarketingTask]:
        stmt = select(MarketingTask).order_by(MarketingTask.updated_at.desc())
        if owner_id is not None:
            stmt = stmt.where(MarketingTask.owner_id == owner_id)
        return list(db.scalars(stmt).all())

    def get_task(self, db: Session, task_id: int, owner_id: int | None = None) -> MarketingTask:
        task = db.get(MarketingTask, task_id)
        if not task or (owner_id is not None and task.owner_id != owner_id):
            raise ValueError("Task not found")
        return task

    async def create_task(
        self,
        db: Session,
        name: str,
        content: str,
        session_group_id: int | None,
        messages_per_target: int,
        send_interval_min: int,
        send_interval_max: int,
        targets_file: UploadFile,
        image: UploadFile | None = None,
        content_material_id: int | None = None,
        image_material_id: int | None = None,
        contact_material_id: int | None = None,
        customer_profile_id: int | None = None,
        send_type: str = "single",
        material_group_id: int | None = None,
        material_group_ids: str | None = None,
        target_type: str = "phone",
        target_source: str = "imported",
        owner_id: int | None = None,
    ) -> MarketingTask:
        send_interval_min, send_interval_max = self._validate_send_interval(send_interval_min, send_interval_max)
        target_source = self._validate_target_source(target_source)
        target_type = validate_target_type(target_type)
        targets = await self._resolve_targets(db, targets_file, customer_profile_id, target_type, owner_id) if target_source == "imported" else []
        send_type = self._validate_send_type(send_type)
        selected_group_ids: list[int] = []
        if send_type == "group":
            self._validate_material_group(db, material_group_id, owner_id)
            content, image_path, contact_card = "", None, None
        elif send_type == "concat":
            material_group_id = None
            selected_group_ids = self._deserialize_group_ids(material_group_ids)
            self._validate_concat_groups(db, selected_group_ids, owner_id)
            content, image_path, contact_card = "", None, None
        else:
            material_group_id = None
            if content_material_id:
                material = material_service.get_material(db, content_material_id, owner_id)
                content = material.content or content
            image_path = await self._resolve_image_path(db, image, image_material_id, owner_id)
            contact_card = self._resolve_contact_card(db, contact_material_id, owner_id)
            if not content.strip() and not image_path and not contact_card:
                raise ValueError("Task content, image or contact card is required")
        task = MarketingTask(
            owner_id=owner_id,
            name=name,
            content=content,
            session_group_id=session_group_id,
            messages_per_target=messages_per_target,
            send_interval_min=send_interval_min,
            send_interval_max=send_interval_max,
            target_type=target_type,
            target_source=target_source,
            targets_text="\n".join(targets),
            total_targets=len(targets),
            image_path=image_path,
            contact_card=contact_card,
            send_type=send_type,
            material_group_id=material_group_id,
            material_group_ids=json.dumps(selected_group_ids) if send_type == "concat" else None,
        )
        db.add(task)
        db.commit()
        db.refresh(task)
        return task

    async def update_task(
        self,
        db: Session,
        task_id: int,
        name: str,
        content: str,
        session_group_id: int | None,
        messages_per_target: int,
        send_interval_min: int,
        send_interval_max: int,
        targets_file: UploadFile | None = None,
        image: UploadFile | None = None,
        content_material_id: int | None = None,
        image_material_id: int | None = None,
        contact_material_id: int | None = None,
        customer_profile_id: int | None = None,
        send_type: str = "single",
        material_group_id: int | None = None,
        material_group_ids: str | None = None,
        target_type: str = "phone",
        target_source: str = "imported",
        owner_id: int | None = None,
    ) -> MarketingTask:
        task = self.get_task(db, task_id, owner_id)
        if task.status in {"queued", "running", "paused", "cancelling"}:
            raise ValueError("Queued or running tasks cannot be edited")
        task.name = name
        send_type = self._validate_send_type(send_type)
        task.send_type = send_type
        if send_type == "group":
            self._validate_material_group(db, material_group_id, owner_id)
            task.material_group_id = material_group_id
            task.material_group_ids = None
            task.content = ""
            task.image_path = None
            task.contact_card = None
        elif send_type == "concat":
            selected_group_ids = self._deserialize_group_ids(material_group_ids)
            self._validate_concat_groups(db, selected_group_ids, owner_id)
            task.material_group_id = None
            task.material_group_ids = json.dumps(selected_group_ids)
            task.content = ""
            task.image_path = None
            task.contact_card = None
        else:
            task.material_group_id = None
            task.material_group_ids = None
            if content_material_id:
                material = material_service.get_material(db, content_material_id, owner_id)
                task.content = material.content or content
            else:
                task.content = content
        task.session_group_id = session_group_id
        task.messages_per_target = messages_per_target
        task.send_interval_min, task.send_interval_max = self._validate_send_interval(send_interval_min, send_interval_max)
        target_source = self._validate_target_source(target_source)
        target_type = validate_target_type(target_type)
        if target_source == "contacts":
            task.targets_text = ""
            task.total_targets = 0
        elif targets_file or customer_profile_id:
            targets = await self._resolve_targets(db, targets_file, customer_profile_id, target_type, owner_id)
            task.targets_text = "\n".join(targets)
            task.total_targets = len(targets)
        elif (task.target_source or "imported") == "contacts":
            raise ValueError("切换到导入数据时必须重新导入TXT或选择客户资料")
        elif target_type != (task.target_type or "phone"):
            raise ValueError("Changing target type requires a new target TXT file or customer profile")
        task.target_type = target_type
        task.target_source = target_source
        if send_type == "single":
            image_path = await self._resolve_image_path(db, image, image_material_id, owner_id)
            if image_path:
                task.image_path = image_path
            contact_card = self._resolve_contact_card(db, contact_material_id, owner_id)
            if contact_material_id is not None:
                task.contact_card = contact_card
            if not task.content.strip() and not task.image_path and not task.contact_card:
                raise ValueError("Task content, image or contact card is required")
        db.commit()
        db.refresh(task)
        return task

    def delete_task(self, db: Session, task_id: int, owner_id: int | None = None) -> None:
        task = self.get_task(db, task_id, owner_id)
        if task.status in {"queued", "running", "paused", "cancelling"}:
            raise ValueError("Running or queued tasks cannot be deleted")
        db.delete(task)
        db.commit()

    def list_task_logs(
        self,
        db: Session,
        task_id: int,
        page: int = 1,
        page_size: int = 50,
        status: str | None = None,
        keyword: str | None = None,
        owner_id: int | None = None,
    ) -> dict[str, Any]:
        self.get_task(db, task_id, owner_id)
        filters = [SessionTaskLog.task_id == task_id]
        if status:
            filters.append(SessionTaskLog.status == status)
        if keyword:
            pattern = f"%{keyword.strip()}%"
            filters.append(or_(SessionTaskLog.target_phone.like(pattern), SessionTaskLog.message.like(pattern)))
        total = db.scalar(select(func.count(SessionTaskLog.id)).where(*filters)) or 0
        page = max(page, 1)
        page_size = min(max(page_size, 1), 200)
        stmt = (
            select(SessionTaskLog, TelegramSession)
            .join(TelegramSession, SessionTaskLog.session_id == TelegramSession.id, isouter=True)
            .where(*filters)
            .order_by(SessionTaskLog.created_at.desc(), SessionTaskLog.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        items = [
            {
                "id": log.id,
                "task_id": log.task_id,
                "task_name": log.task_name,
                "session_id": log.session_id,
                "session_name": session.session_name if session else None,
                "session_phone": session.phone if session else None,
                "target_phone": log.target_phone,
                "target_customer": log.target_phone,
                "status": log.status,
                "message": log.message,
                "sent_at": log.created_at.isoformat() if log.created_at else None,
            }
            for log, session in db.execute(stmt).all()
        ]
        return {"items": items, "total": total, "page": page, "page_size": page_size}

    def list_remaining_targets(self, db: Session, task_id: int, owner_id: int | None = None) -> tuple[MarketingTask, list[str]]:
        task = self.get_task(db, task_id, owner_id)
        if task.status not in {"completed", "completed_with_errors", "failed"}:
            raise ValueError("Task must be finished before exporting remaining targets")
        targets = parse_targets(task.targets_text, task.target_type)
        attempted_targets = set(
            db.scalars(
                select(SessionTaskLog.target_phone).where(
                    SessionTaskLog.task_id == task.id,
                    SessionTaskLog.target_phone.is_not(None),
                )
            ).all()
        )
        attempted_targets.update(
            db.scalars(
                select(TaskTarget.target).where(
                    TaskTarget.task_id == task.id,
                    TaskTarget.status.in_(["processing", "success", "failed", "uncertain"]),
                )
            ).all()
        )
        remaining = [target for target in targets if target not in attempted_targets]
        return task, remaining

    def prepare_queued_task(
        self,
        db: Session,
        task_id: int,
        owner_id: int | None = None,
    ) -> tuple[MarketingTask, list[int]]:
        """Persist unique target assignments and return one durable job per Session."""
        task = self.get_task(db, task_id, owner_id)
        if task.status in {"queued", "running"}:
            raise ValueError("Task is already queued or running")
        target_source = self._validate_target_source(task.target_source or "imported")
        target_type = validate_target_type(task.target_type)
        all_targets = parse_targets(task.targets_text, target_type) if target_source == "imported" else []
        if target_source == "imported" and not all_targets:
            raise ValueError("No valid targets")

        if (task.send_type or "single") == "group":
            queued_group_materials = self._validate_material_group(db, task.material_group_id, owner_id)
            queued_concat_groups: list[list[Material]] = []
        elif task.send_type == "concat":
            queued_group_materials = []
            queued_concat_groups = self._validate_concat_groups(db, self._deserialize_group_ids(task.material_group_ids), owner_id)
        else:
            queued_group_materials = []
            queued_concat_groups = []

        session_stmt = select(TelegramSession).where(TelegramSession.status == SessionStatus.connected)
        if owner_id is not None:
            session_stmt = session_stmt.where(TelegramSession.owner_id == owner_id)
        if task.session_group_id:
            session_stmt = session_stmt.where(TelegramSession.group_id == task.session_group_id)
        sessions = list(db.scalars(session_stmt.order_by(TelegramSession.created_at.asc(), TelegramSession.id.asc())).all())
        if not sessions:
            raise ValueError("No connected sessions in selected group")

        db.execute(delete(TaskTarget).where(TaskTarget.task_id == task.id, TaskTarget.status.in_(["unassigned", "cancelled"])))
        db.flush()
        recorded_targets = set(
            db.scalars(select(TaskTarget.target).where(TaskTarget.task_id == task.id)).all()
        )
        recorded_targets.update(
            db.scalars(
                select(SessionTaskLog.target_phone).where(
                    SessionTaskLog.task_id == task.id,
                    SessionTaskLog.target_phone.is_not(None),
                )
            ).all()
        )
        if target_source == "contacts" and recorded_targets:
            raise ValueError("联系人好友任务已经分配过目标，不能重复执行")
        remaining = [target for target in all_targets if target not in recorded_targets]
        if target_source == "imported" and not remaining:
            raise ValueError("This task has no unprocessed targets")

        quota = max(task.messages_per_target, 1)
        assignable = remaining[: len(sessions) * quota]
        session_ids: list[int] = []
        cursor = 0
        material_queue: list[Material] = []
        target_rows: list[dict[str, Any]] = []
        for session in sessions:
            assigned = (
                [f"__contact_slot__:{session.id}:{index}" for index in range(quota)]
                if target_source == "contacts"
                else assignable[cursor : cursor + quota]
            )
            if not assigned:
                break
            session_ids.append(session.id)
            for target in assigned:
                payload_json = None
                if queued_group_materials:
                    if not material_queue:
                        material_queue = self._weighted_random_order(queued_group_materials)
                    payload_json = json.dumps([self._material_payload(material_queue.pop(0))], ensure_ascii=False)
                elif queued_concat_groups:
                    payload_json = json.dumps([self._concat_payload(queued_concat_groups)], ensure_ascii=False)
                target_rows.append({
                    "task_id": task.id,
                    "session_id": session.id,
                    "target": target,
                    "payload_json": payload_json,
                    "status": "queued",
                    "attempt_count": 0,
                })
            cursor += len(assigned)

        if target_source == "contacts":
            task.total_targets = len(target_rows)

        if target_rows:
            db.execute(insert(TaskTarget), target_rows)
        db.add(TaskOutbox(
            task_id=task.id,
            event_type="enqueue",
            payload_json=json.dumps({"task_id": task.id, "session_ids": session_ids}),
            status="pending",
        ))

        task.status = "queued"
        task.error_message = None
        task.last_run_at = datetime.utcnow()
        db.commit()
        db.refresh(task)
        return task, session_ids

    def pause_task(self, db: Session, task_id: int, owner_id: int | None = None) -> MarketingTask:
        task = self.get_task(db, task_id, owner_id)
        if task.status not in {"queued", "running"}:
            raise ValueError("Only queued or running tasks can be paused")
        task.status = "paused"
        db.commit()
        db.refresh(task)
        return task

    def resume_task(self, db: Session, task_id: int, owner_id: int | None = None) -> MarketingTask:
        task = self.get_task(db, task_id, owner_id)
        if task.status != "paused":
            raise ValueError("Only paused tasks can be resumed")
        session_ids = self._queued_session_ids(db, task.id)
        if not session_ids:
            raise ValueError("Task has no queued Session jobs")
        task.status = "queued"
        self._add_outbox(db, task.id, session_ids, "resume")
        db.commit()
        db.refresh(task)
        return task

    def cancel_task(self, db: Session, task_id: int, owner_id: int | None = None) -> MarketingTask:
        task = self.get_task(db, task_id, owner_id)
        if task.status not in {"queued", "running", "paused", "cancelling"}:
            raise ValueError("Task is not active")
        now = datetime.utcnow()
        db.execute(update(TaskTarget).where(
            TaskTarget.task_id == task.id,
            TaskTarget.status == "queued",
        ).values(status="cancelled", error_message="任务已取消，未发送", finished_at=now))
        processing = db.scalar(select(func.count(TaskTarget.id)).where(
            TaskTarget.task_id == task.id,
            TaskTarget.status == "processing",
        )) or 0
        task.status = "cancelling" if processing else "cancelled"
        task.error_message = "任务已由用户取消"
        db.commit()
        db.refresh(task)
        return task

    def requeue_session_job(
        self,
        db: Session,
        task_id: int,
        session_id: int,
        owner_id: int | None = None,
    ) -> MarketingTask:
        task = self.get_task(db, task_id, owner_id)
        if task.status in {"queued", "running", "cancelling"}:
            raise ValueError("Wait for the active task to stop before requeuing a Session")
        session = db.get(TelegramSession, session_id)
        if not session or session.owner_id != task.owner_id or session.status != SessionStatus.connected:
            raise ValueError("Session is unavailable or not connected")
        rows = list(db.scalars(select(TaskTarget).where(
            TaskTarget.task_id == task.id,
            TaskTarget.session_id == session_id,
            TaskTarget.status.in_(["unassigned", "cancelled"]),
        )).all())
        if not rows:
            raise ValueError("This Session has no definitely unsent targets")
        for row in rows:
            row.status = "queued"
            row.error_message = None
            row.started_at = None
            row.finished_at = None
        task.status = "queued"
        task.error_message = None
        self._add_outbox(db, task.id, [session_id], "requeue_session")
        db.commit()
        db.refresh(task)
        return task

    def active_task_sessions(self, db: Session, task_id: int, owner_id: int | None = None) -> list[dict[str, Any]]:
        self.get_task(db, task_id, owner_id)
        rows = db.execute(
            select(TaskTarget, TelegramSession)
            .join(TelegramSession, TaskTarget.session_id == TelegramSession.id)
            .where(TaskTarget.task_id == task_id, TaskTarget.status == "processing")
            .order_by(TaskTarget.started_at.asc())
        ).all()
        return [{
            "session_id": session.id,
            "session_name": session.session_name,
            "session_phone": session.phone,
            "target": target.target,
            "started_at": target.started_at.isoformat() if target.started_at else None,
        } for target, session in rows]

    def task_session_jobs(self, db: Session, task_id: int, owner_id: int | None = None) -> list[dict[str, Any]]:
        self.get_task(db, task_id, owner_id)
        rows = db.execute(
            select(TelegramSession, TaskTarget.status, func.count(TaskTarget.id))
            .join(TaskTarget, TaskTarget.session_id == TelegramSession.id)
            .where(TaskTarget.task_id == task_id)
            .group_by(TelegramSession.id, TaskTarget.status)
            .order_by(TelegramSession.id.asc())
        ).all()
        jobs: dict[int, dict[str, Any]] = {}
        for session, status, count in rows:
            job = jobs.setdefault(session.id, {
                "session_id": session.id,
                "session_name": session.session_name,
                "session_phone": session.phone,
                "session_status": session.status.value,
                "counts": {},
                "requeueable": 0,
            })
            job["counts"][status] = int(count)
            if status in {"unassigned", "cancelled"}:
                job["requeueable"] += int(count)
        return list(jobs.values())

    def task_stats(self, db: Session, task: MarketingTask) -> dict[str, Any]:
        grouped = {
            status: count
            for status, count in db.execute(
                select(TaskTarget.status, func.count(TaskTarget.id))
                .where(TaskTarget.task_id == task.id)
                .group_by(TaskTarget.status)
            ).all()
        }
        success = int(grouped.get("success", 0))
        failed = int(grouped.get("failed", 0))
        processing = int(grouped.get("processing", 0))
        uncertain = int(grouped.get("uncertain", 0))
        queued = int(grouped.get("queued", 0))
        assigned = sum(int(value) for value in grouped.values())
        unprocessed = max(task.total_targets - success - failed - processing - uncertain, 0)
        cutoff = datetime.utcnow() - timedelta(minutes=5)
        recent_success = db.scalar(select(func.count(TaskTarget.id)).where(
            TaskTarget.task_id == task.id,
            TaskTarget.status == "success",
            TaskTarget.finished_at >= cutoff,
        )) or 0
        elapsed_minutes = 5.0
        if task.last_run_at and task.last_run_at > cutoff:
            elapsed_minutes = max((datetime.utcnow() - task.last_run_at).total_seconds() / 60, 1 / 60)
        speed = round(float(recent_success) / elapsed_minutes, 2)
        eta_minutes = round(unprocessed / speed) if speed > 0 and unprocessed else 0 if not unprocessed else None

        assigned_session_ids = select(TaskTarget.session_id).where(
            TaskTarget.task_id == task.id,
            TaskTarget.session_id.is_not(None),
        )
        throttled_sessions = db.scalar(select(func.count(func.distinct(TelegramSession.id))).where(
            TelegramSession.id.in_(assigned_session_ids),
            or_(TelegramSession.health_status == "restricted", TelegramSession.status == SessionStatus.error),
        )) or 0
        group_ids = set(db.scalars(select(TelegramSession.group_id).where(
            TelegramSession.id.in_(assigned_session_ids), TelegramSession.group_id.is_not(None)
        )).all())
        abnormal_proxies = 0
        for proxy in db.scalars(select(ProxyConfig).where(ProxyConfig.owner_id == task.owner_id)).all():
            proxy_groups = {int(value) for value in proxy_service._deserialize_group_ids(proxy.group_ids) if value.isdigit()}
            if proxy_groups.intersection(group_ids) and proxy.status in {"unreachable", "error", "unhealthy"}:
                abnormal_proxies += 1
        return {
            "assigned": assigned,
            "queued": queued,
            "processing": processing,
            "success": success,
            "failed": failed,
            "unprocessed": unprocessed,
            "uncertain": uncertain,
            "cancelled": int(grouped.get("cancelled", 0)),
            "throttled_sessions": int(throttled_sessions),
            "abnormal_proxies": abnormal_proxies,
            "current_concurrency": processing,
            "speed_per_minute": speed,
            "eta_minutes": eta_minutes,
        }

    def _queued_session_ids(self, db: Session, task_id: int) -> list[int]:
        values = db.scalars(select(TaskTarget.session_id).where(
            TaskTarget.task_id == task_id,
            TaskTarget.status == "queued",
            TaskTarget.session_id.is_not(None),
        ).distinct()).all()
        return [int(value) for value in values]

    def _add_outbox(self, db: Session, task_id: int, session_ids: list[int], event_type: str) -> None:
        db.add(TaskOutbox(
            task_id=task_id,
            event_type=event_type,
            payload_json=json.dumps({"task_id": task_id, "session_ids": session_ids}),
            status="pending",
        ))

    async def process_session_job(self, task_id: int, session_id: int) -> None:
        """Use one Telegram connection to process every queued target assigned to a Session."""
        from app.core.database import SessionLocal
        from app.services.incoming_listener import incoming_message_listener

        db = SessionLocal()
        client: Any | None = None
        owns_client = False
        operation_acquired = False
        try:
            task = db.get(MarketingTask, task_id)
            session = db.get(TelegramSession, session_id)
            if not task or not session:
                return
            targets = list(
                db.scalars(
                    select(TaskTarget).where(
                        TaskTarget.task_id == task_id,
                        TaskTarget.session_id == session_id,
                        TaskTarget.status.in_(["queued", "processing"]),
                    ).order_by(TaskTarget.id.asc())
                ).all()
            )
            if not targets:
                await self._finish_background_task(db, task)
                return

            if task.status in {"paused", "cancelling", "cancelled"}:
                await self._finish_background_task(db, task)
                return

            if task.status == "queued":
                db.execute(update(MarketingTask).where(
                    MarketingTask.id == task.id,
                    MarketingTask.status == "queued",
                ).values(status="running"))
            db.commit()
            db.refresh(task)
            if task.status != "running":
                await self._finish_background_task(db, task)
                return

            await incoming_message_listener.acquire_client_operation(session.id)
            operation_acquired = True
            client = incoming_message_listener.get_connected_client(session.id)
            if client is None:
                await incoming_message_listener.pause_session(session.id)
                client = build_client(session.session_name, proxy_service.get_proxy_url_for_session(db, session))
                owns_client = True
                await asyncio.wait_for(client.connect(), timeout=10)
                if not await asyncio.wait_for(client.is_user_authorized(), timeout=10):
                    raise RuntimeError("Session is not authorized")
            elif not await asyncio.wait_for(client.is_user_authorized(), timeout=10):
                raise RuntimeError("Session is not authorized")

            for item_index, item in enumerate(targets):
                db.refresh(task)
                db.refresh(item)
                if task.status in {"paused", "cancelling", "cancelled"}:
                    break
                if item.status != "queued":
                    continue
                item.status = "processing"
                item.started_at = datetime.utcnow()
                item.attempt_count += 1
                db.commit()
                try:
                    payload_data = json.loads(item.payload_json) if item.payload_json else None
                    contact_data = payload_data.get("contact") if isinstance(payload_data, dict) else None
                    payloads = payload_data.get("materials") if isinstance(payload_data, dict) else payload_data
                    if (task.target_source or "imported") == "contacts" and not contact_data:
                        await self._assign_contact_targets(db, client, task, session, targets)
                        db.refresh(item)
                        payload_data = json.loads(item.payload_json) if item.payload_json else {}
                        contact_data = payload_data.get("contact")
                        payloads = payload_data.get("materials")
                    if (task.target_source or "imported") == "contacts" and not contact_data:
                        continue
                    display_target = contact_data.get("display") if contact_data else item.target
                    is_contact_target = (task.target_source or "imported") == "contacts"
                    delivery_target_type = "username" if is_contact_target else task.target_type
                    session_customer = None if is_contact_target else self._find_session_customer(db, display_target, task.target_type, session.id)
                    sent_meta = await self._send_message_with_client(
                        client,
                        display_target,
                        task.content,
                        task.image_path,
                        task.contact_card,
                        delivery_target_type,
                        contact_data.get("tg_id") if contact_data else (session_customer.tg_id if session_customer else None),
                        contact_data.get("access_hash") if contact_data else (session_customer.access_hash if session_customer else None),
                        payloads,
                    )
                    customer = customer_service.upsert_customer_from_task(
                        db=db,
                        target=display_target,
                        target_type="contact" if is_contact_target else task.target_type,
                        session=session,
                        tg_id=sent_meta.get("tg_id"),
                        nickname=sent_meta.get("nickname"),
                        access_hash=sent_meta.get("access_hash"),
                        username=sent_meta.get("username"),
                        phone_number=sent_meta.get("phone_number"),
                        owner_id=task.owner_id,
                    )
                    outbound_payloads = payloads or [{"content": task.content, "image_path": task.image_path, "contact_card": task.contact_card}]
                    message_ids = sent_meta.get("message_ids") or []
                    for payload_index, payload in enumerate(outbound_payloads):
                        db.add(Message(
                            session_id=session.id,
                            chat_id=customer.tg_id or item.target,
                            telegram_message_id=message_ids[payload_index] if payload_index < len(message_ids) else None,
                            sender=session.username,
                            content=payload["content"] or self._contact_card_message(payload["contact_card"]),
                            image_path=payload["image_path"],
                            direction="outbound",
                            read_status="sent",
                        ))
                    item.status = "success"
                    item.error_message = None
                    item.finished_at = datetime.utcnow()
                    self._log_session_task(db, session.id, task, display_target, "success", "后台队列发送成功")
                    db.execute(update(MarketingTask).where(MarketingTask.id == task.id).values(sent_count=MarketingTask.sent_count + 1))
                    db.commit()
                except Exception as exc:
                    error = self._translate_send_error(exc)
                    item.status = "failed"
                    item.error_message = error[:2000]
                    item.finished_at = datetime.utcnow()
                    self._log_session_task(db, session.id, task, item.target, "failed", f"发送失败，不换号重试：{error}")
                    db.execute(update(MarketingTask).where(MarketingTask.id == task.id).values(failed_count=MarketingTask.failed_count + 1))
                    if self._is_session_restricted_error(exc):
                        self._mark_session_restricted(db, session, error)
                        for remaining in targets:
                            if remaining.status == "queued":
                                remaining.status = "unassigned"
                                remaining.error_message = "Session受限，未尝试发送"
                        db.commit()
                        break
                    db.commit()
                if item_index < len(targets) - 1:
                    delay = random.uniform(task.send_interval_min or 0, task.send_interval_max or 0)
                    if delay > 0:
                        await asyncio.sleep(delay)
            await self._finish_background_task(db, task)
        except Exception as exc:
            if 'task' in locals() and task:
                error = self._translate_send_error(exc)
                for item in db.scalars(select(TaskTarget).where(
                    TaskTarget.task_id == task_id,
                    TaskTarget.session_id == session_id,
                    TaskTarget.status.in_(["queued", "processing"]),
                )).all():
                    item.status = "unassigned"
                    item.error_message = error[:2000]
                task.error_message = error[:2000]
                db.commit()
                await self._finish_background_task(db, task)
        finally:
            if owns_client and client is not None:
                try:
                    if client.is_connected():
                        await client.disconnect()
                finally:
                    await incoming_message_listener.resume_session(session_id)
            if operation_acquired:
                incoming_message_listener.release_client_operation(session_id)
            db.close()

    async def _finish_background_task(self, db: Session, task: MarketingTask) -> None:
        active = db.scalar(select(func.count(TaskTarget.id)).where(
            TaskTarget.task_id == task.id,
            TaskTarget.status.in_(["queued", "processing"]),
        )) or 0
        if active:
            return
        db.refresh(task)
        if task.status in {"cancelling", "cancelled"}:
            db.execute(update(MarketingTask).where(
                MarketingTask.id == task.id,
                MarketingTask.status == "cancelling",
            ).values(status="cancelled"))
            db.commit()
            return
        if task.status == "paused":
            return
        failed = db.scalar(select(func.count(TaskTarget.id)).where(
            TaskTarget.task_id == task.id,
            TaskTarget.status.in_(["failed", "unassigned", "uncertain"]),
        )) or 0
        values: dict[str, Any] = {"status": "completed_with_errors" if failed else "completed"}
        if failed and not task.error_message:
            values["error_message"] = f"{failed} 个目标发送失败或未处理"
        elif not failed:
            values["error_message"] = None
        db.execute(update(MarketingTask).where(
            MarketingTask.id == task.id,
            MarketingTask.status.in_(["running", "queued"]),
        ).values(**values))
        db.commit()

    async def execute_task(self, db: Session, task_id: int, owner_id: int | None = None) -> MarketingTask:
        task = self.get_task(db, task_id, owner_id)
        target_type = validate_target_type(task.target_type)
        all_targets = parse_targets(task.targets_text, target_type)
        if not all_targets:
            task.status = "failed"
            task.error_message = "No valid targets"
            db.commit()
            db.refresh(task)
            return task
        attempted_targets = set(
            db.scalars(
                select(SessionTaskLog.target_phone).where(
                    SessionTaskLog.task_id == task.id,
                    SessionTaskLog.target_phone.is_not(None),
                )
            ).all()
        )
        targets = [target for target in all_targets if target not in attempted_targets]
        if not targets:
            if task.status == "running":
                task.status = "completed"
                task.error_message = None
                db.commit()
                db.refresh(task)
            return task

        group_materials: list[Material] = []
        concat_material_groups: list[list[Material]] = []
        if (task.send_type or "single") == "group":
            try:
                group_materials = self._validate_material_group(db, task.material_group_id, owner_id)
            except ValueError as exc:
                task.status = "failed"
                task.error_message = str(exc)
                db.commit()
                db.refresh(task)
                return task
        elif task.send_type == "concat":
            try:
                concat_material_groups = self._validate_concat_groups(
                    db,
                    self._deserialize_group_ids(task.material_group_ids),
                    owner_id,
                )
            except ValueError as exc:
                task.status = "failed"
                task.error_message = str(exc)
                db.commit()
                db.refresh(task)
                return task

        stmt = select(TelegramSession).where(TelegramSession.status == SessionStatus.connected)
        if owner_id is not None:
            stmt = stmt.where(TelegramSession.owner_id == owner_id)
        if task.session_group_id:
            stmt = stmt.where(TelegramSession.group_id == task.session_group_id)
        stmt = stmt.order_by(TelegramSession.created_at.asc(), TelegramSession.id.asc())
        sessions = list(db.scalars(stmt).all())
        if not sessions:
            task.status = "failed"
            task.error_message = "No connected sessions in selected group"
            db.commit()
            db.refresh(task)
            return task

        task.status = "running"
        task.sent_count = 0
        task.failed_count = 0
        task.error_message = None
        task.last_run_at = datetime.utcnow()
        db.commit()
        db.refresh(task)

        session_index = 0
        available_sessions = sessions.copy()
        per_session_quota = max(task.messages_per_target, 1)
        session_sent_counts = {session.id: 0 for session in sessions}
        target_index = 0
        group_material_queue: list[Material] = []

        while target_index < len(targets) and self._has_session_quota(available_sessions, session_sent_counts, per_session_quota):
            target = targets[target_index]
            if group_materials:
                if not group_material_queue:
                    group_material_queue = self._weighted_random_order(group_materials)
                payloads = [self._material_payload(group_material_queue[0])]
            elif concat_material_groups:
                payloads = [self._concat_payload(concat_material_groups)]
            else:
                payloads = None
            sent = False
            last_error = ""
            attempts = 0
            ordered_sessions = [
                session
                for session in self._ordered_sessions_for_target(available_sessions, session_index)
                if session_sent_counts.get(session.id, 0) < per_session_quota
            ]
            # A target is assigned to exactly one Session. Never retry the same
            # customer with another Session, which could create duplicate sends.
            max_attempts = min(len(ordered_sessions), 1)

            while ordered_sessions and attempts < max_attempts and not sent:
                session = ordered_sessions[attempts]
                session_index += 1
                attempts += 1
                try:
                    session_customer = self._find_session_customer(db, target, target_type, session.id)
                    proxy_url = proxy_service.get_proxy_url_for_session(db, session)
                    sent_meta = await self._send_message(
                        session,
                        target,
                        task.content,
                        task.image_path,
                        task.contact_card,
                        proxy_url,
                        target_type,
                        session_customer.tg_id if session_customer else None,
                        session_customer.access_hash if session_customer else None,
                        payloads,
                    )
                    customer = customer_service.upsert_customer_from_task(
                        db=db,
                        target=target,
                        target_type=target_type,
                        session=session,
                        tg_id=sent_meta.get("tg_id"),
                        nickname=sent_meta.get("nickname"),
                        access_hash=sent_meta.get("access_hash"),
                        username=sent_meta.get("username"),
                        phone_number=sent_meta.get("phone_number"),
                        owner_id=owner_id,
                    )
                    outbound_payloads = payloads or [{"content": task.content, "image_path": task.image_path, "contact_card": task.contact_card}]
                    sent_message_ids = sent_meta.get("message_ids") or []
                    for payload_index, payload in enumerate(outbound_payloads):
                        db.add(
                            Message(
                                session_id=session.id,
                                chat_id=customer.tg_id or target,
                                telegram_message_id=sent_message_ids[payload_index] if payload_index < len(sent_message_ids) else None,
                                sender=session.username,
                                content=payload["content"] or self._contact_card_message(payload["contact_card"]),
                                image_path=payload["image_path"],
                                direction="outbound",
                                read_status="sent",
                            )
                        )
                    session_sent_counts[session.id] = session_sent_counts.get(session.id, 0) + 1
                    task.sent_count += 1
                    if group_materials and group_material_queue:
                        group_material_queue.pop(0)
                    self._log_session_task(
                        db,
                        session.id,
                        task,
                        target,
                        "success",
                        f"发送成功，本Session已发送 {session_sent_counts[session.id]}/{per_session_quota}",
                    )
                    sent = True
                except Exception as exc:
                    last_error = self._translate_send_error(exc)
                    if self._is_session_restricted_error(exc):
                        self._mark_session_restricted(db, session, last_error)
                        self._log_session_task(
                            db,
                            session.id,
                            task,
                            target,
                            "failed",
                            f"Session受限，该客户不再换号重试：{last_error}",
                        )
                        available_sessions = [item for item in available_sessions if item.id != session.id]
                        ordered_sessions = [item for item in ordered_sessions if item.id != session.id]
                        db.commit()
                        continue
                    self._log_session_task(
                        db,
                        session.id,
                        task,
                        target,
                        "failed",
                        f"发送失败，不计入本Session成功数量，该客户不再换号重试：{last_error}",
                    )
                    db.commit()
                    continue

            if not sent:
                task.failed_count += 1
                task.error_message = last_error or "No usable connected sessions in selected group."
                self._log_session_task(db, None, task, target, "failed", f"发送失败：{task.error_message}")
            db.commit()
            target_index += 1

        task.status = "completed" if task.failed_count == 0 else "completed_with_errors"
        db.commit()
        db.refresh(task)
        return task

    def serialize_task(self, task: MarketingTask, db: Session | None = None) -> dict[str, Any]:
        targets = parse_targets(task.targets_text, task.target_type)
        payload = {
            "id": task.id,
            "name": task.name,
            "content": task.content,
            "image_path": task.image_path,
            "contact_card": self._load_contact_card(task.contact_card),
            "send_type": task.send_type or "single",
            "material_group_id": task.material_group_id,
            "material_group_ids": self._deserialize_group_ids(task.material_group_ids),
            "session_group_id": task.session_group_id,
            "target_type": task.target_type or "phone",
            "target_source": task.target_source or "imported",
            "targets": targets,
            "messages_per_target": task.messages_per_target,
            "send_interval_min": task.send_interval_min if task.send_interval_min is not None else 3,
            "send_interval_max": task.send_interval_max if task.send_interval_max is not None else 5,
            "status": task.status,
            "total_targets": task.total_targets,
            "sent_count": task.sent_count,
            "failed_count": task.failed_count,
            "error_message": task.error_message,
            "last_run_at": task.last_run_at.isoformat() if task.last_run_at else None,
            "created_at": task.created_at.isoformat() if task.created_at else None,
            "updated_at": task.updated_at.isoformat() if task.updated_at else None,
        }
        if db is not None:
            payload["stats"] = self.task_stats(db, task)
        return payload

    async def _send_message(
        self,
        session: TelegramSession,
        target_phone: str,
        content: str,
        image_path: str | None,
        contact_card: str | None,
        proxy_url: str | None,
        target_type: str,
        target_tg_id: str | None = None,
        target_access_hash: str | None = None,
        payloads: list[dict[str, str | None]] | None = None,
    ) -> dict[str, Any]:
        from app.services.incoming_listener import incoming_message_listener

        await incoming_message_listener.pause_session(session.id)
        client = build_client(session.session_name, proxy_url)
        try:
            await asyncio.wait_for(client.connect(), timeout=10)
            if not await asyncio.wait_for(client.is_user_authorized(), timeout=10):
                raise RuntimeError("Session is not authorized")
            return await self._send_message_with_client(
                client, target_phone, content, image_path, contact_card, target_type,
                target_tg_id, target_access_hash, payloads,
            )
        finally:
            if client.is_connected():
                await client.disconnect()
            await incoming_message_listener.resume_session(session.id)

    async def _send_message_with_client(
        self,
        client: Any,
        target: str,
        content: str,
        image_path: str | None,
        contact_card: str | None,
        target_type: str,
        target_tg_id: str | None = None,
        target_access_hash: str | None = None,
        payloads: list[dict[str, str | None]] | None = None,
    ) -> dict[str, Any]:
        entity = await self._resolve_target_entity(client, target, target_type, target_tg_id, target_access_hash)
        outbound_payloads = payloads or [{"content": content, "image_path": image_path, "contact_card": contact_card}]
        sent_message_ids: list[int | None] = []
        for payload in outbound_payloads:
            try:
                message_id = await self._send_payload(client, entity, payload)
            except Exception as exc:
                if target_type != "phone" or not self._is_invalid_peer_error(exc):
                    raise
                entity = await self._resolve_target_entity(client, target, target_type, None, None, force_contact=True)
                message_id = await self._send_payload(client, entity, payload)
            sent_message_ids.append(message_id)
        nickname = " ".join(part for part in [getattr(entity, "first_name", None), getattr(entity, "last_name", None)] if part)
        entity_id = getattr(entity, "id", None) or getattr(entity, "user_id", None)
        access_hash = getattr(entity, "access_hash", None)
        username = normalize_username(getattr(entity, "username", None))
        phone_number = getattr(entity, "phone", None)
        if phone_number and not str(phone_number).startswith("+"):
            phone_number = f"+{phone_number}"
        return {
            "tg_id": str(entity_id) if entity_id else target_tg_id,
            "access_hash": str(access_hash) if access_hash else None,
            "username": username or (normalize_username(target) if target_type == "username" else None),
            "phone_number": str(phone_number) if phone_number else (target if target_type == "phone" else None),
            "nickname": nickname or username or target,
            "message_ids": sent_message_ids,
        }

    async def _resolve_target_entity(
        self,
        client: Any,
        target: str,
        target_type: str,
        target_tg_id: str | None = None,
        target_access_hash: str | None = None,
        force_contact: bool = False,
    ) -> Any:
        if not force_contact and target_tg_id and target_access_hash:
            try:
                peer = InputPeerUser(int(target_tg_id), int(target_access_hash))
                return await asyncio.wait_for(client.get_input_entity(peer), timeout=10)
            except Exception:
                pass
        if not force_contact and target_tg_id:
            try:
                tg_candidate: Any = int(target_tg_id) if target_tg_id.isdigit() else target_tg_id
                return await asyncio.wait_for(client.get_entity(tg_candidate), timeout=10)
            except Exception:
                pass
        if not force_contact:
            try:
                return await asyncio.wait_for(client.get_entity(target), timeout=10)
            except Exception:
                if target_type == "username":
                    raise RuntimeError(f"无法解析用户名 {target}")
        if target_type == "username":
            raise RuntimeError(f"无法解析用户名 {target}")
        contact = InputPhoneContact(client_id=0, phone=target, first_name=target, last_name="")
        result = await asyncio.wait_for(client(ImportContactsRequest([contact])), timeout=15)
        if not result.users:
            raise RuntimeError(f"Target {target} is not available to this Session on Telegram")
        return result.users[0]

    async def _send_payload(self, client: Any, entity: Any, payload: dict[str, str | None]) -> int | None:
        content = payload.get("content") or ""
        image_path = payload.get("image_path")
        contact_card = payload.get("contact_card")
        message_id: int | None = None
        if image_path:
            result = await asyncio.wait_for(client.send_file(entity, image_path.lstrip("/"), caption=content.strip() or None), timeout=30)
            message_id = self._sent_message_id(result)
        elif content.strip():
            result = await asyncio.wait_for(client.send_message(entity, content), timeout=30)
            message_id = self._sent_message_id(result)
        if contact_card:
            result = await self._send_contact_card(client, entity, contact_card)
            message_id = self._sent_message_id(result) or message_id
        return message_id

    def _validate_send_type(self, send_type: str) -> str:
        if send_type not in {"single", "group", "concat"}:
            raise ValueError("Send type must be single, group or concat")
        return send_type

    def _validate_send_interval(self, minimum: int, maximum: int) -> tuple[int, int]:
        minimum = 3 if minimum is None else int(minimum)
        maximum = 5 if maximum is None else int(maximum)
        if minimum < 0 or maximum < 0:
            raise ValueError("发送间隔不能小于0秒")
        if maximum < minimum:
            raise ValueError("最大发送间隔不能小于最小发送间隔")
        if maximum > 3600:
            raise ValueError("发送间隔不能超过3600秒")
        return minimum, maximum

    def _validate_target_source(self, target_source: str) -> str:
        if target_source not in {"imported", "contacts"}:
            raise ValueError("Target source must be imported or contacts")
        return target_source

    async def _assign_contact_targets(
        self,
        db: Session,
        client: Any,
        task: MarketingTask,
        session: TelegramSession,
        target_rows: list[TaskTarget],
    ) -> None:
        unresolved = [row for row in target_rows if row.target.startswith("__contact_slot__:") and row.status in {"queued", "processing"}]
        if not unresolved:
            return
        result = await asyncio.wait_for(client(GetContactsRequest(hash=0)), timeout=30)
        users = [user for user in (getattr(result, "users", []) or []) if getattr(user, "id", None)]
        random.shuffle(users)
        used_ids = {
            str((json.loads(row.payload_json) or {}).get("contact", {}).get("tg_id"))
            for row in target_rows if row.payload_json and isinstance(json.loads(row.payload_json), dict)
        }
        available = [user for user in users if str(user.id) not in used_ids]
        shortage = max(len(unresolved) - len(available), 0)
        for index, row in enumerate(unresolved):
            if index >= len(available):
                row.status = "skipped"
                row.error_message = None
                row.finished_at = datetime.utcnow()
                continue
            user = available[index]
            username = normalize_username(getattr(user, "username", None))
            phone = getattr(user, "phone", None)
            if phone and not str(phone).startswith("+"):
                phone = f"+{phone}"
            display = username or phone or str(user.id)
            existing = json.loads(row.payload_json) if row.payload_json else None
            materials = existing if isinstance(existing, list) else (existing or {}).get("materials")
            row.target = f"contact:{session.id}:{user.id}"
            row.payload_json = json.dumps({
                "materials": materials,
                "contact": {
                    "display": display,
                    "tg_id": str(user.id),
                    "access_hash": str(getattr(user, "access_hash", "") or ""),
                    "username": username,
                    "phone": phone,
                },
            }, ensure_ascii=False)
        if shortage:
            db.execute(
                update(MarketingTask)
                .where(MarketingTask.id == task.id)
                .values(total_targets=case(
                    (MarketingTask.total_targets >= shortage, MarketingTask.total_targets - shortage),
                    else_=0,
                ))
            )
        db.commit()

    def _validate_material_group(self, db: Session, group_id: int | None, owner_id: int | None) -> list[Material]:
        if group_id is None:
            raise ValueError("Material group is required")
        materials = material_service.list_group_materials(db, group_id, owner_id)
        if not materials:
            raise ValueError("Selected material group is empty")
        for material in materials:
            if material.material_type == "text" and not (material.content or "").strip():
                raise ValueError(f"Text material '{material.name}' has no content")
            if material.material_type == "image" and not material.file_path:
                raise ValueError(f"Image material '{material.name}' has no image")
            if material.material_type == "contact":
                card = self._load_contact_card(material.content)
                if not card.get("phone_number", "").strip() or not card.get("first_name", "").strip():
                    raise ValueError(f"Contact material '{material.name}' is incomplete")
            if material.material_type not in {"text", "image", "contact"}:
                raise ValueError(f"Material '{material.name}' has an unsupported type")
        return materials

    def _material_payload(self, material: Material) -> dict[str, str | None]:
        if material.material_type == "text":
            return {"content": material.content or "", "image_path": None, "contact_card": None}
        if material.material_type == "image":
            return {"content": "", "image_path": material.file_path, "contact_card": None}
        return {"content": "", "image_path": None, "contact_card": material.content}

    def _validate_concat_groups(
        self,
        db: Session,
        group_ids: list[int],
        owner_id: int | None,
    ) -> list[list[Material]]:
        if len(group_ids) < 2:
            raise ValueError("Concat send requires at least two material groups")
        material_groups: list[list[Material]] = []
        for group_id in group_ids:
            group = material_service.get_group(db, group_id, owner_id)
            text_materials = [
                material
                for material in material_service.list_group_materials(db, group.id, owner_id)
                if material.material_type == "text" and (material.content or "").strip()
            ]
            if not text_materials:
                raise ValueError(f"Material group '{group.name}' has no usable text material")
            material_groups.append(text_materials)
        maximum_length = sum(max(len((material.content or "").strip()) for material in materials) for materials in material_groups)
        if maximum_length > 4096:
            raise ValueError("Concat result may exceed Telegram's 4096-character message limit")
        return material_groups

    def _concat_payload(self, material_groups: list[list[Material]]) -> dict[str, str | None]:
        selected = [self._weighted_random_choice(materials) for materials in material_groups]
        content = "".join((material.content or "").strip() for material in selected)
        return {"content": content, "image_path": None, "contact_card": None}

    def _weighted_random_choice(self, materials: list[Material]) -> Material:
        weights = [max(material.priority, 0) + 1 for material in materials]
        return random.choices(materials, weights=weights, k=1)[0]

    def _deserialize_group_ids(self, value: str | None) -> list[int]:
        if not value:
            return []
        try:
            raw_ids = json.loads(value)
        except (TypeError, json.JSONDecodeError) as exc:
            raise ValueError("Invalid concat material group selection") from exc
        if not isinstance(raw_ids, list):
            raise ValueError("Invalid concat material group selection")
        group_ids: list[int] = []
        for raw_id in raw_ids:
            try:
                group_id = int(raw_id)
            except (TypeError, ValueError) as exc:
                raise ValueError("Invalid concat material group selection") from exc
            if group_id > 0 and group_id not in group_ids:
                group_ids.append(group_id)
        return group_ids

    def _weighted_random_order(self, materials: list[Material]) -> list[Material]:
        """Return every material once, with higher priorities more likely to appear earlier."""
        remaining = list(materials)
        ordered: list[Material] = []
        while remaining:
            weights = [max(material.priority, 0) + 1 for material in remaining]
            selected = random.choices(remaining, weights=weights, k=1)[0]
            ordered.append(selected)
            remaining.remove(selected)
        return ordered

    async def _send_contact_card(self, client: Any, entity: Any, contact_card: str) -> Any:
        card = self._load_contact_card(contact_card)
        phone_number = (card.get("phone_number") or "").strip()
        first_name = (card.get("first_name") or "").strip()
        last_name = (card.get("last_name") or "").strip()
        if not phone_number or not first_name:
            raise RuntimeError("Contact card phone number and first name are required")
        media = InputMediaContact(
            phone_number=phone_number,
            first_name=first_name,
            last_name=last_name,
            vcard=card.get("vcard") or "",
        )
        return await asyncio.wait_for(
            client(
                SendMediaRequest(
                    peer=entity,
                    media=media,
                    message="",
                    random_id=random.getrandbits(63),
                )
            ),
            timeout=30,
        )

    def _sent_message_id(self, result: Any) -> int | None:
        direct_id = getattr(result, "id", None)
        if direct_id is not None:
            try:
                return int(direct_id)
            except (TypeError, ValueError):
                pass
        ids: list[int] = []
        for update_item in getattr(result, "updates", []) or []:
            message = getattr(update_item, "message", None)
            value = getattr(message, "id", None) or getattr(update_item, "id", None)
            try:
                if value is not None:
                    ids.append(int(value))
            except (TypeError, ValueError):
                continue
        return max(ids) if ids else None

    def _resolve_contact_card(self, db: Session, contact_material_id: int | None, owner_id: int | None = None) -> str | None:
        if not contact_material_id:
            return None
        material = material_service.get_material(db, contact_material_id, owner_id)
        if material.material_type != "contact":
            raise ValueError("Selected material is not a contact card")
        card = self._load_contact_card(material.content)
        if not (card.get("phone_number") or "").strip() or not (card.get("first_name") or "").strip():
            raise ValueError("Contact card phone number and first name are required")
        return json.dumps(card, ensure_ascii=False)

    def _load_contact_card(self, value: str | None) -> dict[str, str]:
        if not value:
            return {}
        try:
            data = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return {
            "phone_number": str(data.get("phone_number") or ""),
            "first_name": str(data.get("first_name") or ""),
            "last_name": str(data.get("last_name") or ""),
            "vcard": str(data.get("vcard") or ""),
        }

    def _contact_card_message(self, value: str | None) -> str:
        card = self._load_contact_card(value)
        if not card:
            return ""
        name = " ".join(part for part in [card.get("first_name"), card.get("last_name")] if part)
        return f"名片：{name or '-'} {card.get('phone_number') or ''}".strip()

    def _find_session_customer(self, db: Session, target: str, target_type: str, session_id: int) -> Customer | None:
        stmt = select(Customer).where(
            Customer.assigned_session_id == session_id,
            Customer.tg_id.is_not(None),
        )
        if target_type == "username":
            stmt = stmt.where(Customer.username == normalize_username(target))
        else:
            stmt = stmt.where(Customer.phone_number == target)
        return db.scalar(stmt.order_by(Customer.updated_at.desc()))

    def _ordered_sessions_for_target(
        self,
        sessions: list[TelegramSession],
        session_index: int,
    ) -> list[TelegramSession]:
        if not sessions:
            return []
        return [sessions[(session_index + offset) % len(sessions)] for offset in range(len(sessions))]

    def _has_session_quota(
        self,
        sessions: list[TelegramSession],
        session_sent_counts: dict[int, int],
        per_session_quota: int,
    ) -> bool:
        return any(session_sent_counts.get(session.id, 0) < per_session_quota for session in sessions)

    def _is_session_restricted_error(self, exc: Exception) -> bool:
        message = str(exc).upper()
        restricted_markers = (
            "FROZEN_METHOD_INVALID",
            "USER_DEACTIVATED",
            "USER_DEACTIVATED_BAN",
            "PHONE_NUMBER_BANNED",
            "AUTH_KEY_UNREGISTERED",
            "SESSION_REVOKED",
            "FLOOD_WAIT",
            "PEER_FLOOD",
        )
        return any(marker in message for marker in restricted_markers)

    def _translate_send_error(self, exc: Exception | str) -> str:
        raw = str(exc).strip()
        upper = raw.upper()
        translations = [
            (("ALLOW_PAYMENT_REQUIRED",), "目标客户开启了付费消息，当前发送需要支付 Telegram Stars"),
            (("FROZEN_METHOD_INVALID",), "Session账号已被冻结，Telegram禁止执行发送操作"),
            (("AUTH_KEY_DUPLICATED",), "Session授权在不同IP同时使用，授权密钥已失效"),
            (("AUTH_KEY_UNREGISTERED", "SESSION_REVOKED", "SESSION_EXPIRED"), "Session登录授权已失效，需要重新登录"),
            (("USER_PRIVACY_RESTRICTED",), "目标客户的隐私设置不允许当前账号发送消息"),
            (("USER_NOT_MUTUAL_CONTACT",), "目标客户仅允许互为联系人后发送消息"),
            (("CONTACT_REQUIRE_PREMIUM", "PREMIUM_ACCOUNT_REQUIRED"), "目标客户要求发送方使用 Telegram Premium账号"),
            (("PEER_FLOOD",), "Session触发Telegram垃圾消息风控，暂时禁止继续私聊陌生用户"),
            (("USER_BANNED_IN_CHANNEL",), "Session已被目标群组或频道封禁"),
            (("CHAT_WRITE_FORBIDDEN",), "当前Session没有向该会话发送消息的权限"),
            (("CHAT_SEND_MEDIA_FORBIDDEN", "CHAT_SEND_PHOTOS_FORBIDDEN"), "当前会话禁止发送图片或媒体"),
            (("INPUT_USER_DEACTIVATED", "USER_DEACTIVATED", "USER_DEACTIVATED_BAN"), "目标Telegram账号已注销或被封禁"),
            (("USERNAME_NOT_OCCUPIED",), "目标用户名不存在或已被注销"),
            (("USERNAME_INVALID",), "目标用户名格式无效"),
            (("PHONE_NUMBER_INVALID",), "目标手机号格式无效"),
            (("PEER_ID_INVALID", "USER_ID_INVALID", "INPUT_USER_INVALID"), "目标客户无效，当前Session无法解析该用户"),
            (("MESSAGE_TOO_LONG",), "发送文字超过Telegram允许的最大长度"),
            (("MEDIA_EMPTY", "MEDIA_INVALID", "PHOTO_INVALID", "IMAGE_PROCESS_FAILED"), "图片或媒体文件无效，Telegram无法处理"),
            (("FILE_REFERENCE_EXPIRED",), "媒体文件引用已过期，需要重新上传"),
            (("SLOWMODE_WAIT",), "目标会话开启慢速模式，需要稍后再发送"),
            (("BOT_METHOD_INVALID",), "当前操作不支持机器人账号"),
            (("YOU_BLOCKED_USER",), "当前Session已屏蔽目标客户"),
            (("USER_IS_BLOCKED",), "目标客户已屏蔽当前Session"),
            (("DATABASE IS LOCKED",), "Session文件正在被其他连接占用"),
            (("SESSION IS NOT AUTHORIZED", "NOT AUTHORIZED"), "Session未登录或授权已失效"),
            (("IS NOT AVAILABLE TO THIS SESSION",), "当前Session无法找到该目标客户的Telegram账号"),
            (("无法解析用户名",), "无法解析目标用户名，用户可能不存在或已更名"),
            (("TIMED OUT", "TIMEOUT", "TIMEOUTERROR"), "连接Telegram超时，请检查代理或网络稳定性"),
            (("SERVER CLOSED THE CONNECTION", "CONNECTION ERROR", "NETWORK ERROR"), "Telegram网络连接异常，请检查代理或网络"),
            (("RPC_CALL_FAIL", "INTERNAL_SERVER_ERROR", "SERVER_ERROR"), "Telegram服务器暂时异常，请稍后重试"),
        ]
        for tokens, text in translations:
            matched = next((token for token in tokens if token.upper() in upper), None)
            if matched:
                detail = text
                if matched == "SLOWMODE_WAIT":
                    seconds = re.search(r"SLOWMODE_WAIT[_\s-]?(\d+)", upper)
                    if seconds:
                        detail += f"（需等待约 {seconds.group(1)} 秒）"
                code = matched if matched.isascii() and " " not in matched else None
                return f"{detail}{f'（错误码：{code}）' if code else ''}"

        flood = re.search(r"FLOOD_WAIT[_\s-]?(\d+)?", upper)
        if flood or "A WAIT OF" in upper:
            seconds = flood.group(1) if flood else None
            detail = "Telegram发送频率过高，需要等待后再发送"
            if seconds:
                detail += f"（约 {seconds} 秒）"
            return f"{detail}（错误码：FLOOD_WAIT）"
        return f"Telegram发送失败：{raw[:500] or '未知错误'}"

    def _is_invalid_peer_error(self, exc: Exception) -> bool:
        message = str(exc).upper()
        return "INVALID PEER" in message or "PEER_ID_INVALID" in message

    def _mark_session_restricted(self, db: Session, session: TelegramSession, message: str) -> None:
        session.status = SessionStatus.error
        session.health_status = "restricted"
        session.error_message = message[:2000]
        session.last_health_check_at = datetime.utcnow()

    async def _save_upload(self, upload: UploadFile | None, directory: str) -> str | None:
        if not upload or not upload.filename:
            return None
        return await save_compressed_image(upload, directory)

    async def _resolve_image_path(self, db: Session, image: UploadFile | None, image_material_id: int | None, owner_id: int | None = None) -> str | None:
        if image_material_id:
            material = material_service.get_material(db, image_material_id, owner_id)
            return material.file_path
        if image:
            return await self._save_upload(image, "static/task_images")
        return None

    async def _resolve_targets(
        self,
        db: Session,
        targets_file: UploadFile | None,
        customer_profile_id: int | None,
        target_type: str,
        owner_id: int | None = None,
    ) -> list[str]:
        if customer_profile_id:
            profile = db.get(CustomerProfile, customer_profile_id)
            if not profile or (owner_id is not None and profile.owner_id != owner_id):
                raise ValueError("Customer profile not found")
            if (profile.target_type or "phone") != target_type:
                raise ValueError("Customer profile type does not match task target type")
            return parse_targets(profile.content, target_type)
        if not targets_file:
            raise ValueError("Targets file or customer profile is required")
        targets = parse_targets(await targets_file.read(), target_type)
        if not targets:
            label = "phone numbers" if target_type == "phone" else "usernames"
            raise ValueError(f"No valid {label} found in target TXT")
        return targets

    def _log_session_task(self, db: Session, session_id: int, task: MarketingTask, target_phone: str, status: str, message: str) -> None:
        db.add(
            SessionTaskLog(
                session_id=session_id,
                task_id=task.id,
                task_name=task.name,
                target_phone=target_phone,
                status=status,
                message=message,
            )
        )


task_service = TaskService()
