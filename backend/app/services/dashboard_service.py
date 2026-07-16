from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models.customer import Customer
from app.models.customer_profile import CustomerProfile
from app.models.material import Material, MaterialGroup
from app.models.message import Message
from app.models.session import SessionGroup, TelegramSession
from app.models.task import MarketingTask


class DashboardService:
    def get_statistics(self, db: Session, owner_id: int) -> dict[str, Any]:
        sessions = self._session_statistics(db, owner_id)
        messages = self._message_statistics(db, owner_id)
        materials = self._material_statistics(db, owner_id)
        customer_profiles = self._customer_profile_statistics(db, owner_id)
        tasks = self._task_statistics(db, owner_id)
        return {
            "generated_at": datetime.utcnow().isoformat(),
            "overview": {
                "sessions": sessions["total"],
                "conversations": messages["conversations"],
                "materials": materials["total"],
                "customer_targets": customer_profiles["total_targets"],
                "tasks": tasks["total"],
            },
            "sessions": sessions,
            "messages": messages,
            "materials": materials,
            "customer_profiles": customer_profiles,
            "tasks": tasks,
        }

    def _session_statistics(self, db: Session, owner_id: int) -> dict[str, Any]:
        status = self._group_counts(db, TelegramSession.status, TelegramSession.owner_id == owner_id)
        bidirectional = self._group_counts(db, TelegramSession.bidirectional_status, TelegramSession.owner_id == owner_id)
        group_rows = db.execute(
            select(SessionGroup.name, func.count(TelegramSession.id))
            .select_from(TelegramSession)
            .join(SessionGroup, TelegramSession.group_id == SessionGroup.id, isouter=True)
            .where(TelegramSession.owner_id == owner_id)
            .group_by(SessionGroup.id, SessionGroup.name)
            .order_by(func.count(TelegramSession.id).desc())
        ).all()
        total = sum(status.values())
        return {
            "total": total,
            "connected": status.get("connected", 0),
            "offline": max(total - status.get("connected", 0), 0),
            "status": status,
            "bidirectional": bidirectional,
            "groups": [{"name": name or "未分组", "value": int(count)} for name, count in group_rows],
        }

    def _message_statistics(self, db: Session, owner_id: int) -> dict[str, Any]:
        # Keep dashboard message totals aligned with the customer conversation
        # list. A Telegram session can also receive group/channel/system
        # messages; those rows do not belong to a customer chat and must not be
        # included here.
        customer_message = select(Customer.id).where(
            Customer.owner_id == owner_id,
            Customer.send_status != "unknown",
            Customer.assigned_session_id == Message.session_id,
            or_(
                Message.chat_id == Customer.tg_id.collate("utf8mb4_unicode_ci"),
                Message.chat_id == Customer.username.collate("utf8mb4_unicode_ci"),
                Message.chat_id == Customer.phone_number.collate("utf8mb4_unicode_ci"),
            ),
        ).exists()
        direction = self._group_counts(
            db,
            Message.direction,
            TelegramSession.owner_id == owner_id,
            customer_message,
            join_model=TelegramSession,
            join_condition=Message.session_id == TelegramSession.id,
        )
        conversation_filter = (Customer.owner_id == owner_id, Customer.send_status != "unknown")
        reply_status = self._group_counts(db, Customer.reply_status, *conversation_filter)
        conversations = sum(reply_status.values())
        favorites = int(db.scalar(select(func.count(Customer.id)).where(
            *conversation_filter, Customer.is_favorite.is_(True)
        )) or 0)
        unread = int(db.scalar(
            select(func.count(Message.id))
            .join(TelegramSession, Message.session_id == TelegramSession.id)
            .where(
                TelegramSession.owner_id == owner_id,
                customer_message,
                Message.direction == "inbound",
                Message.read_status == "unread",
            )
        ) or 0)
        today_start = datetime.combine(date.today(), datetime.min.time())
        today_messages = int(db.scalar(
            select(func.count(Message.id))
            .join(TelegramSession, Message.session_id == TelegramSession.id)
            .where(
                TelegramSession.owner_id == owner_id,
                customer_message,
                Message.created_at >= today_start,
            )
        ) or 0)
        trend_start = today_start - timedelta(days=6)
        trend_rows = db.execute(
            select(func.date(Message.created_at), Message.direction, func.count(Message.id))
            .join(TelegramSession, Message.session_id == TelegramSession.id)
            .where(
                TelegramSession.owner_id == owner_id,
                customer_message,
                Message.created_at >= trend_start,
            )
            .group_by(func.date(Message.created_at), Message.direction)
        ).all()
        trend_map = {(str(day), direction_name): int(count) for day, direction_name, count in trend_rows}
        trend = []
        for offset in range(7):
            day = (trend_start + timedelta(days=offset)).date().isoformat()
            trend.append({
                "date": day,
                "inbound": trend_map.get((day, "inbound"), 0),
                "outbound": trend_map.get((day, "outbound"), 0),
            })
        return {
            "conversations": conversations,
            "favorites": favorites,
            "replied": reply_status.get("replied", 0),
            "not_replied": reply_status.get("not_replied", 0),
            "total": sum(direction.values()),
            "inbound": direction.get("inbound", 0),
            "outbound": direction.get("outbound", 0),
            "unread": unread,
            "today": today_messages,
            "direction": direction,
            "reply_status": reply_status,
            "trend": trend,
        }

    def _material_statistics(self, db: Session, owner_id: int) -> dict[str, Any]:
        types = self._group_counts(db, Material.material_type, Material.owner_id == owner_id)
        return {
            "total": sum(types.values()),
            "groups": int(db.scalar(select(func.count(MaterialGroup.id)).where(MaterialGroup.owner_id == owner_id)) or 0),
            "types": types,
        }

    def _customer_profile_statistics(self, db: Session, owner_id: int) -> dict[str, Any]:
        rows = db.execute(
            select(
                CustomerProfile.target_type,
                func.count(CustomerProfile.id),
                func.coalesce(func.sum(CustomerProfile.total_count), 0),
            )
            .where(CustomerProfile.owner_id == owner_id)
            .group_by(CustomerProfile.target_type)
        ).all()
        types = {
            str(target_type or "unknown"): {"profiles": int(profile_count), "targets": int(target_count)}
            for target_type, profile_count, target_count in rows
        }
        return {
            "total": sum(item["profiles"] for item in types.values()),
            "total_targets": sum(item["targets"] for item in types.values()),
            "types": types,
        }

    def _task_statistics(self, db: Session, owner_id: int) -> dict[str, Any]:
        status = self._group_counts(db, MarketingTask.status, MarketingTask.owner_id == owner_id)
        task_rows = db.execute(
            select(
                MarketingTask.id,
                MarketingTask.name,
                MarketingTask.status,
                MarketingTask.total_targets,
                MarketingTask.sent_count,
                MarketingTask.failed_count,
            )
            .where(MarketingTask.owner_id == owner_id)
            .order_by(MarketingTask.created_at.desc(), MarketingTask.id.desc())
        ).all()
        totals = db.execute(
            select(
                func.coalesce(func.sum(MarketingTask.total_targets), 0),
                func.coalesce(func.sum(MarketingTask.sent_count), 0),
                func.coalesce(func.sum(MarketingTask.failed_count), 0),
            ).where(MarketingTask.owner_id == owner_id)
        ).one()
        target_count, sent_count, failed_count = (int(value or 0) for value in totals)
        processed = sent_count + failed_count
        return {
            "total": sum(status.values()),
            "active": sum(status.get(item, 0) for item in ("queued", "running", "paused", "cancelling")),
            "completed": status.get("completed", 0),
            "total_targets": target_count,
            "sent": sent_count,
            "failed": failed_count,
            "remaining": max(target_count - processed, 0),
            "success_rate": round(sent_count * 100 / processed, 1) if processed else 0,
            "progress_rate": round(processed * 100 / target_count, 1) if target_count else 0,
            "status": status,
            "items": [
                {
                    "id": task_id,
                    "name": name,
                    "status": self._value(task_status),
                    "total_targets": int(task_targets or 0),
                    "sent": int(task_sent or 0),
                    "failed": int(task_failed or 0),
                }
                for task_id, name, task_status, task_targets, task_sent, task_failed in task_rows
            ],
        }

    def _group_counts(
        self,
        db: Session,
        column: Any,
        *conditions: Any,
        join_model: Any | None = None,
        join_condition: Any | None = None,
    ) -> dict[str, int]:
        stmt = select(column, func.count()).select_from(column.class_)
        if join_model is not None:
            stmt = stmt.join(join_model, join_condition)
        rows = db.execute(stmt.where(*conditions).group_by(column)).all()
        return {
            self._value(key) if key is not None else "unknown": int(count)
            for key, count in rows
        }

    def _value(self, value: Any) -> str:
        return str(value.value if hasattr(value, "value") else value)


dashboard_service = DashboardService()
