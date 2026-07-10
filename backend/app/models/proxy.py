from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ProxyConfig(Base):
    __tablename__ = "proxies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    owner_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(100), index=True)
    scheme: Mapped[str] = mapped_column(String(20), default="http", index=True)
    host: Mapped[str] = mapped_column(String(255), index=True)
    port: Mapped[int] = mapped_column(Integer)
    username: Mapped[str | None] = mapped_column(String(150), nullable=True)
    password: Mapped[str | None] = mapped_column(String(255), nullable=True)
    color: Mapped[str] = mapped_column(String(20), default="blue")
    is_active: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    group_ids: Mapped[str | None] = mapped_column(String(500), nullable=True)
    session_ids: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_check_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


__all__ = ["ProxyConfig"]
