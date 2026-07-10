from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    owner_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    phone_number: Mapped[str] = mapped_column(String(32), index=True)
    tg_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    access_hash: Mapped[str | None] = mapped_column(String(100), nullable=True)
    nickname: Mapped[str | None] = mapped_column(String(150), nullable=True)
    avatar: Mapped[str | None] = mapped_column(String(500), nullable=True)
    assigned_session_id: Mapped[int | None] = mapped_column(ForeignKey("sessions.id", ondelete="SET NULL"), nullable=True, index=True)
    kf_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    send_status: Mapped[str] = mapped_column(String(30), default="pending", index=True)
    reply_status: Mapped[str] = mapped_column(String(30), default="not_replied", index=True)
    remark: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


Index("ix_customers_phone_session", Customer.phone_number, Customer.assigned_session_id)
