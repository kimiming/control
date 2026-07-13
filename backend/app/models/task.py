from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
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


__all__ = ["MarketingTask"]
