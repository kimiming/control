import asyncio
import json
import random
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.orm import Session, aliased
from telethon.tl.functions.messages import SendMediaRequest
from telethon.tl.functions.contacts import ImportContactsRequest
from telethon.tl.types import InputMediaContact, InputPeerUser, InputPhoneContact

from app.core.cache import redis_client
from app.models.customer import Customer
from app.models.material import Material
from app.models.message import Message
from app.models.session import SessionStatus, TelegramSession
from app.models.support_agent import SupportAgent
from app.services.material_service import material_service
from app.services.proxy_service import proxy_service
from app.services.target_parser import normalize_username
from app.services.session_command_bus import session_command_bus


class CustomerService:
    def list_customers(
        self,
        db: Session,
        kf_id: int | None = None,
        keyword: str | None = None,
        reply_status: str | None = None,
        is_favorite: bool | None = None,
        owner_id: int | None = None,
        source: str | None = None,
    ) -> list[dict[str, Any]]:
        stmt = self._customer_list_stmt(kf_id, keyword, reply_status, is_favorite, owner_id, source)
        return [
            self.serialize_customer(db, customer, session, agent, source=source)
            for customer, session, agent in db.execute(stmt).all()
        ]

    def list_customer_page(
        self,
        db: Session,
        page: int = 1,
        page_size: int = 20,
        kf_id: int | None = None,
        keyword: str | None = None,
        reply_status: str | None = None,
        is_favorite: bool | None = None,
        owner_id: int | None = None,
        source: str | None = None,
    ) -> dict[str, Any]:
        stmt = self._customer_list_stmt(kf_id, keyword, reply_status, is_favorite, owner_id, source)
        count_stmt = select(func.count()).select_from(stmt.order_by(None).subquery())
        total = int(db.scalar(count_stmt) or 0)
        rows = db.execute(stmt.offset((page - 1) * page_size).limit(page_size)).all()
        return {
            "items": [
                self.serialize_customer(db, customer, session, agent, source=source)
                for customer, session, agent in rows
            ],
            "page": page,
            "page_size": page_size,
            "total": total,
            "has_more": page * page_size < total,
        }

    def count_customer_conversations(
        self,
        db: Session,
        kf_id: int | None = None,
        keyword: str | None = None,
        reply_status: str | None = None,
        owner_id: int | None = None,
        source: str | None = None,
    ) -> dict[str, int]:
        all_stmt = self._customer_list_stmt(kf_id, keyword, reply_status, None, owner_id, source)
        favorite_stmt = self._customer_list_stmt(kf_id, keyword, reply_status, True, owner_id, source)
        return {
            "all": int(db.scalar(select(func.count()).select_from(all_stmt.order_by(None).subquery())) or 0),
            "favorites": int(db.scalar(select(func.count()).select_from(favorite_stmt.order_by(None).subquery())) or 0),
        }

    def _customer_list_stmt(
        self,
        kf_id: int | None,
        keyword: str | None,
        reply_status: str | None,
        is_favorite: bool | None,
        owner_id: int | None,
        source: str | None = None,
    ) -> Any:
        stmt = (
            select(Customer, TelegramSession, SupportAgent)
            .join(TelegramSession, Customer.assigned_session_id == TelegramSession.id, isouter=True)
            .join(SupportAgent, TelegramSession.kf_id == SupportAgent.id, isouter=True)
            .where(
                Customer.send_status != "unknown",
                or_(Customer.tg_id.is_(None), Customer.tg_id.not_in(("333000", "777000"))),
                or_(Customer.phone_number.is_(None), Customer.phone_number.not_in(("+42777", "42777"))),
            )
        )
        duplicate = aliased(Customer)
        same_identity = or_(
            and_(
                Customer.tg_id.is_not(None),
                duplicate.tg_id == Customer.tg_id,
            ),
            and_(
                Customer.tg_id.is_(None),
                Customer.username.is_not(None),
                duplicate.tg_id.is_(None),
                duplicate.username == Customer.username,
            ),
            and_(
                Customer.tg_id.is_(None),
                Customer.username.is_(None),
                Customer.phone_number.is_not(None),
                duplicate.tg_id.is_(None),
                duplicate.username.is_(None),
                duplicate.phone_number == Customer.phone_number,
            ),
            and_(
                Customer.tg_id.is_(None),
                Customer.username.is_(None),
                Customer.phone_number.is_(None),
                duplicate.id == Customer.id,
            ),
        )
        canonical_customer_id = (
            select(func.max(duplicate.id))
            .where(
                duplicate.owner_id == Customer.owner_id,
                duplicate.assigned_session_id == Customer.assigned_session_id,
                same_identity,
            )
            .correlate(Customer)
            .scalar_subquery()
        )
        stmt = stmt.where(Customer.id == canonical_customer_id)
        if owner_id is not None:
            stmt = stmt.where(Customer.owner_id == owner_id)
        if kf_id is not None:
            stmt = stmt.where(TelegramSession.kf_id == kf_id)
        has_unread_inbound = select(Message.id).where(
            Message.session_id == Customer.assigned_session_id,
            Message.direction == "inbound",
            Message.read_status == "unread",
            or_(
                Message.chat_id == Customer.tg_id.collate("utf8mb4_unicode_ci"),
                Message.chat_id == Customer.username.collate("utf8mb4_unicode_ci"),
                Message.chat_id == Customer.phone_number.collate("utf8mb4_unicode_ci"),
            ),
        ).exists()
        latest_outbound_status = (
            select(Message.read_status)
            .where(
                Message.session_id == Customer.assigned_session_id,
                Message.direction == "outbound",
                or_(
                    Message.chat_id == Customer.tg_id.collate("utf8mb4_unicode_ci"),
                    Message.chat_id == Customer.username.collate("utf8mb4_unicode_ci"),
                    Message.chat_id == Customer.phone_number.collate("utf8mb4_unicode_ci"),
                ),
            )
            .order_by(Message.created_at.desc(), Message.id.desc())
            .limit(1)
            .scalar_subquery()
        )
        if source == "task":
            task_message_exists = select(Message.id).where(
                Message.session_id == Customer.assigned_session_id,
                Message.source == "task",
                or_(
                    Message.chat_id == Customer.tg_id.collate("utf8mb4_unicode_ci"),
                    Message.chat_id == Customer.username.collate("utf8mb4_unicode_ci"),
                    Message.chat_id == Customer.phone_number.collate("utf8mb4_unicode_ci"),
                ),
            ).exists()
            stmt = stmt.where(task_message_exists)
        if reply_status == "replied":
            stmt = stmt.where(or_(Customer.reply_status == "replied", has_unread_inbound))
        elif reply_status == "not_replied":
            stmt = stmt.where(Customer.reply_status == "not_replied", ~has_unread_inbound)
        elif reply_status == "peer_read":
            stmt = stmt.where(
                Customer.reply_status == "not_replied",
                latest_outbound_status == "read",
                ~has_unread_inbound,
            )
        elif reply_status == "peer_unread":
            stmt = stmt.where(
                Customer.reply_status == "not_replied",
                latest_outbound_status.is_not(None),
                latest_outbound_status != "read",
                ~has_unread_inbound,
            )
        if is_favorite is not None:
            favorite_column = Customer.is_task_favorite if source == "task" else Customer.is_favorite
            stmt = stmt.where(favorite_column == is_favorite)
        if keyword:
            like = f"%{keyword}%"
            stmt = stmt.where(
                or_(
                    Customer.phone_number.like(like),
                    Customer.username.like(like),
                    Customer.nickname.like(like),
                    Customer.tg_id.like(like),
                )
            )
        stmt = stmt.order_by(Customer.last_message_at.is_(None), Customer.last_message_at.desc(), Customer.updated_at.desc())
        return stmt

    def get_customer(self, db: Session, customer_id: int, owner_id: int | None = None) -> Customer:
        customer = db.get(Customer, customer_id)
        if not customer or (owner_id is not None and customer.owner_id != owner_id):
            raise ValueError("Customer not found")
        return customer

    def set_favorite(
        self,
        db: Session,
        customer_id: int,
        is_favorite: bool,
        owner_id: int | None = None,
        source: str | None = None,
    ) -> Customer:
        customer = self.get_customer(db, customer_id, owner_id)
        if source == "task":
            customer.is_task_favorite = is_favorite
        else:
            customer.is_favorite = is_favorite
        db.commit()
        db.refresh(customer)
        return customer

    async def list_messages_page(
        self,
        db: Session,
        customer_id: int,
        page_size: int = 20,
        before_id: int | None = None,
        owner_id: int | None = None,
        source: str | None = None,
    ) -> dict[str, Any]:
        customer = self.get_customer(db, customer_id, owner_id)
        chat_key = self._chat_key(customer)
        stmt = (
            select(Message)
            .where(Message.session_id == customer.assigned_session_id, Message.chat_id == chat_key)
            .order_by(Message.created_at.desc(), Message.id.desc())
            .limit(page_size + 1)
        )
        if before_id is not None:
            stmt = stmt.where(Message.id < before_id)
        if source == "task":
            task_message = aliased(Message)
            latest_task_sent_at = (
                select(func.max(task_message.created_at))
                .where(
                    task_message.session_id == customer.assigned_session_id,
                    task_message.chat_id == chat_key,
                    task_message.direction == "outbound",
                    task_message.source == "task",
                )
                .scalar_subquery()
            )
            stmt = stmt.where(
                or_(
                    Message.source == "task",
                    and_(
                        Message.direction == "inbound",
                        Message.created_at > latest_task_sent_at,
                    ),
                )
            )
        fetched = list(db.scalars(stmt).all())
        has_more = len(fetched) > page_size
        messages = list(reversed(fetched[:page_size]))
        has_unread = any(item.direction == "inbound" and item.read_status == "unread" for item in messages)
        db.execute(
            update(Message)
            .where(
                Message.session_id == customer.assigned_session_id,
                Message.chat_id == chat_key,
                Message.direction == "inbound",
                Message.read_status == "unread",
            )
            .values(read_status="read")
        )
        db.commit()
        if has_unread:
            session = db.get(TelegramSession, customer.assigned_session_id) if customer.assigned_session_id else None
            if session and session.status == SessionStatus.connected:
                await self._acknowledge_customer_read(session, customer, proxy_service.get_proxy_url_for_session(db, session))
        return {
            "items": [self.serialize_message(item) for item in messages],
            "has_more": has_more,
            # Keep one row of overlap between cursor pages. The newest page is
            # periodically refreshed, so this prevents a message at the moving
            # page boundary from disappearing when a new message arrives.
            "next_before_id": messages[0].id + 1 if has_more and messages else None,
        }

    async def reply(self, db: Session, customer_id: int, text: str | None = None, material_id: int | None = None, owner_id: int | None = None) -> Customer:
        text = (text or "").strip()
        if not text and not material_id:
            raise ValueError("Reply text or material is required")
        customer = self.get_customer(db, customer_id, owner_id)
        if not customer.assigned_session_id:
            raise ValueError("Customer is not assigned to a session")
        session = db.get(TelegramSession, customer.assigned_session_id)
        if not session or session.status != SessionStatus.connected:
            raise ValueError("Assigned session is not connected")

        material = material_service.get_material(db, material_id, owner_id) if material_id else None
        content, image_path, telegram_message_id = await self._send_reply(session, customer, text, material, proxy_service.get_proxy_url_for_session(db, session))
        chat_key = self._chat_key(customer)
        existing_message = None
        if telegram_message_id is not None:
            existing_message = db.scalar(
                select(Message).where(
                    Message.session_id == session.id,
                    Message.chat_id == chat_key,
                    Message.direction == "outbound",
                    Message.telegram_message_id == telegram_message_id,
                )
            )
        if not existing_message:
            db.add(
                Message(
                    session_id=session.id,
                    chat_id=chat_key,
                    telegram_message_id=telegram_message_id,
                    sender=session.username,
                    content=content,
                    image_path=image_path,
                    direction="outbound",
                    source="manual_reply",
                    read_status="sent",
                )
            )
        customer.last_message_at = datetime.utcnow()
        customer.reply_status = "not_replied"
        db.commit()
        db.refresh(customer)
        return customer

    def upsert_customer_from_task(
        self,
        db: Session,
        target: str,
        target_type: str,
        session: TelegramSession,
        tg_id: str | None = None,
        nickname: str | None = None,
        access_hash: str | None = None,
        username: str | None = None,
        phone_number: str | None = None,
        owner_id: int | None = None,
    ) -> Customer:
        username = normalize_username(username) or (normalize_username(target) if target_type == "username" else None)
        phone_number = phone_number or (target if target_type == "phone" else None)
        stmt = select(Customer).where(Customer.assigned_session_id == session.id, Customer.owner_id == owner_id)
        identity_filters = []
        if tg_id:
            identity_filters.append(Customer.tg_id == tg_id)
        if username:
            identity_filters.append(Customer.username == username)
        if phone_number:
            identity_filters.append(Customer.phone_number == phone_number)
        customer = (
            db.scalar(stmt.where(or_(*identity_filters)).order_by(Customer.id.desc()).limit(1))
            if identity_filters
            else None
        )
        if not customer:
            customer = Customer(owner_id=owner_id, phone_number=phone_number, username=username, assigned_session_id=session.id)
            db.add(customer)
        customer.kf_id = session.kf_id
        customer.tg_id = tg_id or customer.tg_id
        customer.access_hash = access_hash or customer.access_hash
        customer.username = username or customer.username
        customer.phone_number = phone_number or customer.phone_number
        customer.nickname = nickname or customer.nickname or username or phone_number or target
        customer.send_status = "success"
        customer.last_message_at = datetime.utcnow()
        db.flush()
        return customer

    def unread_count(self, db: Session, customer: Customer) -> int:
        chat_key = self._chat_key(customer)
        return db.scalar(
            select(func.count(Message.id)).where(
                Message.session_id == customer.assigned_session_id,
                Message.chat_id == chat_key,
                Message.direction == "inbound",
                Message.read_status == "unread",
            )
        ) or 0

    def serialize_customer(
        self,
        db: Session,
        customer: Customer,
        session: TelegramSession | None = None,
        support_agent: SupportAgent | None = None,
        source: str | None = None,
    ) -> dict[str, Any]:
        unread_count = self.unread_count(db, customer)
        reply_status = "replied" if unread_count else customer.reply_status
        if source == "task":
            chat_key = self._chat_key(customer)
            latest_task_sent_at = db.scalar(
                select(func.max(Message.created_at)).where(
                    Message.session_id == customer.assigned_session_id,
                    Message.chat_id == chat_key,
                    Message.direction == "outbound",
                    Message.source == "task",
                )
            )
            has_project_reply = bool(
                latest_task_sent_at
                and db.scalar(
                    select(Message.id)
                    .where(
                        Message.session_id == customer.assigned_session_id,
                        Message.chat_id == chat_key,
                        Message.direction == "inbound",
                        Message.created_at > latest_task_sent_at,
                    )
                    .limit(1)
                )
            )
            reply_status = "replied" if has_project_reply else "not_replied"
        return {
            "id": customer.id,
            "phone_number": customer.phone_number,
            "username": customer.username,
            "tg_id": customer.tg_id,
            "nickname": customer.nickname,
            "avatar": customer.avatar,
            "assigned_session_id": customer.assigned_session_id,
            "assigned_session_name": session.session_name if session else None,
            "assigned_session_status": session.status.value if session and hasattr(session.status, "value") else (session.status if session else None),
            "assigned_session_bidirectional_status": session.bidirectional_status if session else None,
            "assigned_session_bidirectional_detail": session.bidirectional_detail if session else None,
            "assigned_session_last_bidirectional_check_at": session.last_bidirectional_check_at.isoformat() if session and session.last_bidirectional_check_at else None,
            "kf_id": customer.kf_id,
            "kf_name": support_agent.name if support_agent else None,
            "send_status": customer.send_status,
            "reply_status": reply_status,
            "is_favorite": customer.is_task_favorite if source == "task" else customer.is_favorite,
            "unread_count": unread_count,
            "remark": customer.remark,
            "last_message_at": customer.last_message_at.isoformat() if customer.last_message_at else None,
            "created_at": customer.created_at.isoformat() if customer.created_at else None,
            "updated_at": customer.updated_at.isoformat() if customer.updated_at else None,
        }

    def serialize_message(self, message: Message) -> dict[str, Any]:
        return {
            "id": message.id,
            "session_id": message.session_id,
            "chat_id": message.chat_id,
            "telegram_message_id": message.telegram_message_id,
            "sender": message.sender,
            "content": message.content,
            "image_path": message.image_path,
            "direction": message.direction,
            "source": message.source,
            "task_id": message.task_id,
            "read_status": message.read_status,
            "created_at": message.created_at.isoformat(),
        }

    async def _send_reply(
        self,
        session: TelegramSession,
        customer: Customer,
        text: str,
        material: Material | None,
        proxy_url: str | None,
    ) -> tuple[str, str | None, int | None]:
        material_payload = None
        if material:
            material_payload = {
                "name": material.name, "material_type": material.material_type,
                "content": material.content, "file_path": material.file_path,
                "contact_card": self._load_contact_card(material.content) if material.material_type == "contact" else None,
            }
        result = await session_command_bus.execute(session.id, "reply", {
            "tg_id": customer.tg_id, "access_hash": customer.access_hash,
            "username": customer.username, "phone_number": customer.phone_number,
            "text": text, "material": material_payload,
        }, timeout=75)
        return str(result.get("content") or ""), result.get("image_path"), result.get("telegram_message_id")

    async def _acknowledge_customer_read(self, session: TelegramSession, customer: Customer, proxy_url: str | None) -> None:
        try:
            await session_command_bus.execute(session.id, "ack_read", {
                "tg_id": customer.tg_id, "access_hash": customer.access_hash,
                "username": customer.username, "phone_number": customer.phone_number,
            }, timeout=20)
        except Exception:
            return

    async def _send_read_acknowledge(self, client: Any, entity: Any) -> None:
        try:
            await asyncio.wait_for(client.send_read_acknowledge(entity), timeout=15)
        except Exception:
            pass

    async def _send_reply_payload(self, client: Any, entity: Any, text: str, material: Material | None) -> tuple[str, str | None, int | None]:
        if not material:
            result = await asyncio.wait_for(client.send_message(entity, text), timeout=30)
            return text, None, self._sent_message_id(result)

        if material.material_type == "text":
            content = (material.content or text or "").strip()
            if not content:
                raise ValueError("Selected text material is empty")
            result = await asyncio.wait_for(client.send_message(entity, content), timeout=30)
            return content, None, self._sent_message_id(result)

        if material.material_type == "image":
            if not material.file_path:
                raise ValueError("Selected image material has no file")
            file_path = self._local_static_path(material.file_path)
            result = await asyncio.wait_for(client.send_file(entity, file_path, caption=text or ""), timeout=60)
            return text or f"图片素材：{material.name}", material.file_path, self._sent_message_id(result)

        if material.material_type == "contact":
            content = self._contact_card_message(material.content)
            result = await self._send_contact_card(client, entity, material.content)
            sent_id = self._sent_message_id(result)
            if text:
                text_result = await asyncio.wait_for(client.send_message(entity, text), timeout=30)
                sent_id = self._sent_message_id(text_result) or sent_id
                content = f"{content}\n{text}".strip()
            return content, None, sent_id

        raise ValueError("Unsupported material type")

    def _local_static_path(self, value: str) -> str:
        if value.startswith("/static/"):
            return str(Path("static") / value.removeprefix("/static/"))
        return value

    async def _send_contact_card(self, client: Any, entity: Any, contact_card: str | None) -> Any:
        card = self._load_contact_card(contact_card)
        phone_number = (card.get("phone_number") or "").strip()
        first_name = (card.get("first_name") or "").strip()
        last_name = (card.get("last_name") or "").strip()
        if not phone_number or not first_name:
            raise ValueError("Contact card phone number and first name are required")
        username = normalize_username(card.get("username"))
        if username:
            try:
                user = await asyncio.wait_for(client.get_entity(username), timeout=15)
                resolved_phone = str(getattr(user, "phone", "") or "").strip()
                if resolved_phone:
                    phone_number = resolved_phone if resolved_phone.startswith("+") else f"+{resolved_phone}"
            except Exception:
                # Telegram may hide the phone number even when the username resolves.
                # In that case the explicitly entered card phone remains authoritative.
                pass
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

    def _load_contact_card(self, value: str | None) -> dict[str, str]:
        if not value:
            return {}
        try:
            data = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return {
            "phone_number": str(data.get("phone_number") or ""),
            "username": str(data.get("username") or ""),
            "first_name": str(data.get("first_name") or ""),
            "last_name": str(data.get("last_name") or ""),
            "vcard": str(data.get("vcard") or ""),
        }

    def _contact_card_message(self, value: str | None) -> str:
        card = self._load_contact_card(value)
        name = " ".join(part for part in [card.get("first_name"), card.get("last_name")] if part)
        return f"名片：{name or '-'} {card.get('phone_number') or ''}".strip()

    async def _resolve_customer_entity(self, client: Any, customer: Customer) -> Any:
        candidates: list[Any] = []
        if customer.tg_id and customer.access_hash:
            try:
                candidates.append(InputPeerUser(int(customer.tg_id), int(customer.access_hash)))
            except ValueError:
                pass
        if customer.tg_id:
            candidates.append(int(customer.tg_id) if customer.tg_id.isdigit() else customer.tg_id)
        if customer.username:
            candidates.append(customer.username)
        if customer.phone_number:
            candidates.append(customer.phone_number)

        for candidate in candidates:
            try:
                return await asyncio.wait_for(client.get_entity(candidate), timeout=10)
            except Exception:
                continue

        if not customer.phone_number:
            raise RuntimeError("Customer username is not available on Telegram")
        contact = InputPhoneContact(client_id=0, phone=customer.phone_number, first_name=customer.phone_number, last_name="")
        result = await asyncio.wait_for(client(ImportContactsRequest([contact])), timeout=15)
        if not result.users:
            raise RuntimeError("Customer is not available on Telegram")
        return result.users[0]

    def _chat_key(self, customer: Customer) -> str:
        value = customer.tg_id or customer.username or customer.phone_number
        if not value:
            raise ValueError("Customer has no Telegram identifier")
        return value


customer_service = CustomerService()
