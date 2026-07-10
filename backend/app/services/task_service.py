import asyncio
import json
import re
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
from app.services.customer_service import customer_service
from app.services.image_storage import save_compressed_image
from app.services.material_service import material_service
from app.services.proxy_service import proxy_service


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
        owner_id: int | None = None,
    ) -> MarketingTask:
        targets = await self._resolve_targets(db, targets_file, customer_profile_id, owner_id)
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
            targets_text="\n".join(targets),
            total_targets=len(targets),
            image_path=image_path,
            contact_card=contact_card,
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
        owner_id: int | None = None,
    ) -> MarketingTask:
        task = self.get_task(db, task_id, owner_id)
        task.name = name
        if content_material_id:
            material = material_service.get_material(db, content_material_id, owner_id)
            task.content = material.content or content
        else:
            task.content = content
        task.session_group_id = session_group_id
        task.messages_per_target = messages_per_target
        if targets_file or customer_profile_id:
            targets = await self._resolve_targets(db, targets_file, customer_profile_id, owner_id)
            task.targets_text = "\n".join(targets)
            task.total_targets = len(targets)
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

    async def execute_task(self, db: Session, task_id: int, owner_id: int | None = None) -> MarketingTask:
        task = self.get_task(db, task_id, owner_id)
        targets = self._parse_targets(task.targets_text.encode())
        if not targets:
            task.status = "failed"
            task.error_message = "No target phone numbers"
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

        while target_index < len(targets) and self._has_session_quota(available_sessions, session_sent_counts, per_session_quota):
            target = targets[target_index]
            sent = False
            last_error = ""
            attempts = 0
            ordered_sessions = [
                session
                for session in self._ordered_sessions_for_target(available_sessions, session_index)
                if session_sent_counts.get(session.id, 0) < per_session_quota
            ]
            max_attempts = len(ordered_sessions)

            while ordered_sessions and attempts < max_attempts and not sent:
                session = ordered_sessions[attempts]
                session_index += 1
                attempts += 1
                try:
                    session_customer = self._find_session_customer(db, target, session.id)
                    proxy_url = proxy_service.get_proxy_url_for_session(db, session)
                    sent_meta = await self._send_message(
                        session,
                        target,
                        task.content,
                        task.image_path,
                        task.contact_card,
                        proxy_url,
                        session_customer.tg_id if session_customer else None,
                        session_customer.access_hash if session_customer else None,
                    )
                    customer = customer_service.upsert_customer_from_task(
                        db,
                        target,
                        session,
                        sent_meta.get("tg_id"),
                        sent_meta.get("nickname"),
                        sent_meta.get("access_hash"),
                        owner_id,
                    )
                    db.add(
                        Message(
                            session_id=session.id,
                            chat_id=customer.tg_id or target,
                            sender=session.username,
                            content=task.content or self._contact_card_message(task.contact_card),
                            image_path=task.image_path,
                            direction="outbound",
                            read_status="read",
                        )
                    )
                    session_sent_counts[session.id] = session_sent_counts.get(session.id, 0) + 1
                    task.sent_count += 1
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
                            f"Session受限，已跳过并换号重试：{last_error}",
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
                        f"发送失败，不计入本Session已发送数量，继续换号：{last_error}",
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
        targets = self._parse_targets(task.targets_text.encode())
        return {
            "id": task.id,
            "name": task.name,
            "content": task.content,
            "image_path": task.image_path,
            "contact_card": self._load_contact_card(task.contact_card),
            "session_group_id": task.session_group_id,
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
        target_tg_id: str | None = None,
        target_access_hash: str | None = None,
    ) -> dict[str, str | None]:
        from app.services.incoming_listener import incoming_message_listener

        await incoming_message_listener.pause_session(session.id)
        client = build_client(session.session_name, proxy_url)
        try:
            await asyncio.wait_for(client.connect(), timeout=10)
            if not await asyncio.wait_for(client.is_user_authorized(), timeout=10):
                raise RuntimeError("Session is not authorized")
            entity = await self._resolve_target_entity(client, target_phone, target_tg_id, target_access_hash)
            caption = content.strip() or None
            if image_path:
                try:
                    await asyncio.wait_for(client.send_file(entity, image_path.lstrip("/"), caption=caption), timeout=30)
                except Exception as exc:
                    if not self._is_invalid_peer_error(exc):
                        raise
                    entity = await self._resolve_target_entity(client, target_phone, None, None, force_contact=True)
                    await asyncio.wait_for(client.send_file(entity, image_path.lstrip("/"), caption=caption), timeout=30)
            elif content.strip():
                try:
                    await asyncio.wait_for(client.send_message(entity, content), timeout=30)
                except Exception as exc:
                    if not self._is_invalid_peer_error(exc):
                        raise
                    entity = await self._resolve_target_entity(client, target_phone, None, None, force_contact=True)
                    await asyncio.wait_for(client.send_message(entity, content), timeout=30)
            if contact_card:
                try:
                    await self._send_contact_card(client, entity, contact_card)
                except Exception as exc:
                    if not self._is_invalid_peer_error(exc):
                        raise
                    entity = await self._resolve_target_entity(client, target_phone, None, None, force_contact=True)
                    await self._send_contact_card(client, entity, contact_card)
            nickname = " ".join(part for part in [getattr(entity, "first_name", None), getattr(entity, "last_name", None)] if part)
            entity_id = getattr(entity, "id", None) or getattr(entity, "user_id", None)
            access_hash = getattr(entity, "access_hash", None)
            return {
                "tg_id": str(entity_id) if entity_id else target_tg_id,
                "access_hash": str(access_hash) if access_hash else None,
                "nickname": getattr(entity, "username", None) or nickname or target_phone,
            }
        finally:
            if client.is_connected():
                await client.disconnect()
            await incoming_message_listener.resume_session(session.id)

    async def _resolve_target_entity(
        self,
        client: Any,
        target_phone: str,
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
                return await asyncio.wait_for(client.get_entity(target_phone), timeout=10)
            except Exception:
                pass
        contact = InputPhoneContact(client_id=0, phone=target_phone, first_name=target_phone, last_name="")
        result = await asyncio.wait_for(client(ImportContactsRequest([contact])), timeout=15)
        if not result.users:
            raise RuntimeError(f"Target {target_phone} is not available to this Session on Telegram")
        return result.users[0]

    async def _send_contact_card(self, client: Any, entity: Any, contact_card: str) -> None:
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
        await asyncio.wait_for(
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

    def _find_session_customer(self, db: Session, phone: str, session_id: int) -> Customer | None:
        return db.scalar(
            select(Customer)
            .where(
                Customer.phone_number == phone,
                Customer.assigned_session_id == session_id,
                Customer.tg_id.is_not(None),
            )
            .order_by(Customer.updated_at.desc())
        )

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

    def _parse_targets(self, content: bytes) -> list[str]:
        text = content.decode("utf-8-sig", errors="ignore")
        targets: list[str] = []
        seen: set[str] = set()
        for line in text.splitlines():
            match = re.search(r"\+?\d[\d\s().-]{4,}\d", line)
            if not match:
                continue
            phone = re.sub(r"[\s().-]+", "", match.group(0))
            if phone and phone not in seen:
                seen.add(phone)
                targets.append(phone[:32])
        return targets

    async def _resolve_targets(
        self,
        db: Session,
        targets_file: UploadFile | None,
        customer_profile_id: int | None,
        owner_id: int | None = None,
    ) -> list[str]:
        if customer_profile_id:
            profile = db.get(CustomerProfile, customer_profile_id)
            if not profile or (owner_id is not None and profile.owner_id != owner_id):
                raise ValueError("Customer profile not found")
            return self._parse_targets(profile.content.encode())
        if not targets_file:
            raise ValueError("Targets file or customer profile is required")
        return self._parse_targets(await targets_file.read())

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
