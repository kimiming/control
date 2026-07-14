from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class MarketingTask(Base):
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    owner_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(150), index=True)
    content: Mapped[str] = mapped_column(Text)
    image_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    contact_card: Mapped[str | None] = mapped_column(Text, nullable=True)
    send_type: Mapped[str] = mapped_column(String(20), default="single", index=True)
    material_group_id: Mapped[int | None] = mapped_column(ForeignKey("material_groups.id", ondelete="SET NULL"), nullable=True, index=True)
    material_group_ids: Mapped[str | None] = mapped_column(Text, nullable=True)
    session_group_id: Mapped[int | None] = mapped_column(ForeignKey("session_groups.id", ondelete="SET NULL"), nullable=True, index=True)
    target_type: Mapped[str] = mapped_column(String(20), default="phone", index=True)
    target_source: Mapped[str] = mapped_column(String(20), default="imported", index=True)
    targets_text: Mapped[str] = mapped_column(Text)
    messages_per_target: Mapped[int] = mapped_column(Integer, default=3)
    status: Mapped[str] = mapped_column(String(50), default="draft", index=True)
    total_targets: Mapped[int] = mapped_column(Integer, default=0)
    sent_count: Mapped[int] = mapped_column(Integer, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class TaskTarget(Base):
    """Durable assignment and idempotency record for one task target."""

    __tablename__ = "task_targets"
    __table_args__ = (
        UniqueConstraint("task_id", "target", name="uq_task_targets_task_target"),
        Index("ix_task_targets_task_status", "task_id", "status"),
        Index("ix_task_targets_session_status", "session_id", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False, index=True)
    session_id: Mapped[int | None] = mapped_column(ForeignKey("sessions.id", ondelete="SET NULL"), nullable=True, index=True)
    target: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    payload_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="queued", nullable=False, index=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class TaskOutbox(Base):
    """Transactional hand-off from MySQL task state to the Redis queue."""

    __tablename__ = "task_outbox"
    __table_args__ = (Index("ix_task_outbox_status_created", "status", "created_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    task_id: Mapped[int | None] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), nullable=True, index=True)
    event_type: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="pending", nullable=False, index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


__all__ = ["MarketingTask", "TaskTarget", "TaskOutbox"]
