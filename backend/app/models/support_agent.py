from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class SupportAgent(Base):
    __tablename__ = "support_agents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    owner_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    remark: Mapped[str | None] = mapped_column(Text, nullable=True)
    color: Mapped[str] = mapped_column(String(20), default="blue")
    status: Mapped[str] = mapped_column(String(30), default="active", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    sessions: Mapped[list["TelegramSession"]] = relationship(back_populates="support_agent", lazy="selectin")
