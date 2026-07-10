from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.message import Message
from app.models.session import TelegramSession


class MessageService:
    def list_messages(self, db: Session, page: int = 1, page_size: int = 50, session_id: int | None = None, owner_id: int | None = None):
        stmt = select(Message).order_by(Message.created_at.desc())
        if owner_id is not None:
            stmt = stmt.join(TelegramSession, Message.session_id == TelegramSession.id).where(TelegramSession.owner_id == owner_id)
        if session_id:
            stmt = stmt.where(Message.session_id == session_id)
        offset = (page - 1) * page_size
        return list(db.scalars(stmt.offset(offset).limit(page_size)).all())


message_service = MessageService()
