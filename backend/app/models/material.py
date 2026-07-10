from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Material(Base):
    __tablename__ = "materials"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    owner_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(150), index=True)
    material_type: Mapped[str] = mapped_column(String(20), index=True)
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    file_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    priority: Mapped[int] = mapped_column(Integer, default=0, index=True)
    remark: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
