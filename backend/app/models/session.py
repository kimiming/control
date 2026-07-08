from datetime import datetime
from enum import Enum

from sqlalchemy import DateTime, Enum as SqlEnum, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class SessionStatus(str, Enum):
    disconnected = "disconnected"
    connecting = "connecting"
    connected = "connected"
    error = "error"


class SessionGroup(Base):
    __tablename__ = "session_groups"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)

    sessions: Mapped[list["TelegramSession"]] = relationship(back_populates="group", lazy="selectin")


class TelegramSession(Base):
    __tablename__ = "sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    username: Mapped[str] = mapped_column(String(100), index=True)
    avatar: Mapped[str | None] = mapped_column(String(500), nullable=True)
    phone: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    session_name: Mapped[str] = mapped_column(String(150), unique=True, index=True)
    status: Mapped[SessionStatus] = mapped_column(SqlEnum(SessionStatus), default=SessionStatus.disconnected, index=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    last_health_check_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    health_status: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    group_id: Mapped[int | None] = mapped_column(ForeignKey("session_groups.id"), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    group: Mapped[SessionGroup | None] = relationship(back_populates="sessions", lazy="joined")
    logs: Mapped[list["SessionLog"]] = relationship(back_populates="session", cascade="all, delete-orphan", lazy="selectin")


class SessionLog(Base):
    __tablename__ = "session_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    session_id: Mapped[int | None] = mapped_column(ForeignKey("sessions.id", ondelete="SET NULL"), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(50), index=True)
    message: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    operator: Mapped[str | None] = mapped_column(String(100), nullable=True)

    session: Mapped[TelegramSession | None] = relationship(back_populates="logs")


Index("ix_sessions_status_group", TelegramSession.status, TelegramSession.group_id)
Index("ix_session_logs_session_created", SessionLog.session_id, SessionLog.created_at)
