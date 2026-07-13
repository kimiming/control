import asyncio
import json
import random
from datetime import datetime
from typing import Any

from fastapi import UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session
from telethon.tl.functions.messages import SendMediaRequest
from telethon.tl.functions.contacts import ImportContactsRequest
from telethon.tl.types import InputMediaContact, InputPeerUser, InputPhoneContact

from app.core.telegram import build_client
from app.models.customer import Customer
from app.models.customer_profile import CustomerProfile
from app.models.session import SessionStatus, SessionTaskLog, TelegramSession
from app.models.task import MarketingTask
from app.models.message import Message
from app.models.material import Material
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
        owner_id: int | None = None,
    ) -> MarketingTask:
        target_type = validate_target_type(target_type)
        targets = await self._resolve_targets(db, targets_file, customer_profile_id, target_type, owner_id)
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
            target_type=target_type,
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
        owner_id: int | None = None,
    ) -> MarketingTask:
        task = self.get_task(db, task_id, owner_id)
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
        target_type = validate_target_type(target_type)
        if targets_file or customer_profile_id:
            targets = await self._resolve_targets(db, targets_file, customer_profile_id, target_type, owner_id)
            task.targets_text = "\n".join(targets)
            task.total_targets = len(targets)
        elif target_type != (task.target_type or "phone"):
            raise ValueError("Changing target type requires a new target TXT file or customer profile")
        task.target_type = target_type
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
        db.delete(task)
        db.commit()

    def list_task_logs(self, db: Session, task_id: int, limit: int = 500, owner_id: int | None = None) -> list[dict[str, Any]]:
        self.get_task(db, task_id, owner_id)
        stmt = (
            select(SessionTaskLog, TelegramSession)
            .join(TelegramSession, SessionTaskLog.session_id == TelegramSession.id, isouter=True)
            .where(SessionTaskLog.task_id == task_id)
            .order_by(SessionTaskLog.created_at.desc(), SessionTaskLog.id.desc())
            .limit(min(max(limit, 1), 1000))
        )
        return [
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
        remaining = [target for target in targets if target not in attempted_targets]
        return task, remaining

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
                    last_error = str(exc)
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

    def serialize_task(self, task: MarketingTask) -> dict[str, Any]:
        targets = parse_targets(task.targets_text, task.target_type)
        return {
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
            "targets": targets,
            "messages_per_target": task.messages_per_target,
            "status": task.status,
            "total_targets": task.total_targets,
            "sent_count": task.sent_count,
            "failed_count": task.failed_count,
            "error_message": task.error_message,
            "last_run_at": task.last_run_at.isoformat() if task.last_run_at else None,
            "created_at": task.created_at.isoformat() if task.created_at else None,
            "updated_at": task.updated_at.isoformat() if task.updated_at else None,
        }

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
            entity = await self._resolve_target_entity(client, target_phone, target_type, target_tg_id, target_access_hash)
            outbound_payloads = payloads or [{"content": content, "image_path": image_path, "contact_card": contact_card}]
            sent_message_ids: list[int | None] = []
            for payload in outbound_payloads:
                try:
                    message_id = await self._send_payload(client, entity, payload)
                except Exception as exc:
                    if target_type != "phone" or not self._is_invalid_peer_error(exc):
                        raise
                    entity = await self._resolve_target_entity(client, target_phone, target_type, None, None, force_contact=True)
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
                "username": username or (normalize_username(target_phone) if target_type == "username" else None),
                "phone_number": str(phone_number) if phone_number else (target_phone if target_type == "phone" else None),
                "nickname": nickname or username or target_phone,
                "message_ids": sent_message_ids,
            }
        finally:
            if client.is_connected():
                await client.disconnect()
            await incoming_message_listener.resume_session(session.id)

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
        maximum_length += len(material_groups) - 1
        if maximum_length > 4096:
            raise ValueError("Concat result may exceed Telegram's 4096-character message limit")
        return material_groups

    def _concat_payload(self, material_groups: list[list[Material]]) -> dict[str, str | None]:
        selected = [self._weighted_random_choice(materials) for materials in material_groups]
        content = "\n".join((material.content or "").strip() for material in selected)
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
