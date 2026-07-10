from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("sessions.id"), index=True)
    chat_id: Mapped[str] = mapped_column(String(100), index=True)
    telegram_message_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    sender: Mapped[str | None] = mapped_column(String(150), nullable=True)
    content: Mapped[str] = mapped_column(Text)
    image_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    direction: Mapped[str] = mapped_column(String(20), default="inbound", index=True)
    read_status: Mapped[str] = mapped_column(String(20), default="unread", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


Index("ix_messages_session_created", Message.session_id, Message.created_at)
Index("ix_messages_chat_created", Message.chat_id, Message.created_at)
Index("ix_messages_session_chat_tg_msg", Message.session_id, Message.chat_id, Message.telegram_message_id)
