from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.auth import get_current_user, require_any_menu_access
from app.core.database import get_db
from app.models.session import TelegramSession
from app.models.support_agent import SupportAgent
from app.models.user import User


class SupportAgentPayload(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    remark: str | None = None
    color: str = Field(default="blue", pattern="^(red|orange|yellow|green|blue|geekblue|purple)$")
    status: str = Field(default="active", max_length=30)
    session_ids: list[int] | None = None
    group_ids: list[int] | None = None


router = APIRouter(prefix="/support-agents", tags=["support-agents"], dependencies=[Depends(require_any_menu_access("customers", "messages", "sessions", "tasks"))])


@router.get("")
def list_support_agents(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> list[dict[str, Any]]:
    agents = db.scalars(select(SupportAgent).where(SupportAgent.owner_id == user.id).order_by(SupportAgent.created_at.asc())).all()
    return [_serialize_agent(agent) for agent in agents]


@router.post("")
def create_support_agent(payload: SupportAgentPayload, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict[str, Any]:
    exists = db.scalar(select(SupportAgent).where(SupportAgent.name == payload.name, SupportAgent.owner_id == user.id))
    if exists:
        raise HTTPException(status_code=400, detail="客服名称已存在")
    agent = SupportAgent(owner_id=user.id, name=payload.name, remark=payload.remark, color=payload.color or "blue", status=payload.status)
    db.add(agent)
    db.flush()
    _apply_bindings(db, agent.id, payload, user.id)
    db.commit()
    db.refresh(agent)
    return _serialize_agent(agent)


@router.put("/{agent_id}")
def update_support_agent(agent_id: int, payload: SupportAgentPayload, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict[str, Any]:
    agent = db.get(SupportAgent, agent_id)
    if not agent or agent.owner_id != user.id:
        raise HTTPException(status_code=404, detail="客服不存在")
    exists = db.scalar(select(SupportAgent).where(SupportAgent.name == payload.name, SupportAgent.id != agent_id, SupportAgent.owner_id == user.id))
    if exists:
        raise HTTPException(status_code=400, detail="客服名称已存在")
    agent.name = payload.name
    agent.remark = payload.remark
    agent.color = payload.color or "blue"
    agent.status = payload.status
    _apply_bindings(db, agent.id, payload, user.id)
    db.commit()
    db.refresh(agent)
    return _serialize_agent(agent)


@router.delete("/{agent_id}")
def delete_support_agent(agent_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict[str, bool]:
    agent = db.get(SupportAgent, agent_id)
    if not agent or agent.owner_id != user.id:
        raise HTTPException(status_code=404, detail="客服不存在")
    for session in db.scalars(select(TelegramSession).where(TelegramSession.kf_id == agent_id, TelegramSession.owner_id == user.id)).all():
        session.kf_id = None
    db.delete(agent)
    db.commit()
    return {"ok": True}


def _bind_sessions(db: Session, agent_id: int, session_ids: list[int], owner_id: int) -> None:
    normalized_ids = list(dict.fromkeys(session_ids))
    for session in db.scalars(select(TelegramSession).where(TelegramSession.kf_id == agent_id, TelegramSession.owner_id == owner_id)).all():
        session.kf_id = None
    if not normalized_ids:
        return
    sessions = db.scalars(select(TelegramSession).where(TelegramSession.id.in_(normalized_ids), TelegramSession.owner_id == owner_id)).all()
    for session in sessions:
        session.kf_id = agent_id


def _bind_groups(db: Session, agent_id: int, group_ids: list[int], owner_id: int) -> None:
    normalized_ids = list(dict.fromkeys(group_ids))
    for session in db.scalars(select(TelegramSession).where(TelegramSession.kf_id == agent_id, TelegramSession.owner_id == owner_id)).all():
        session.kf_id = None
    if not normalized_ids:
        return

    conditions = []
    real_group_ids = [group_id for group_id in normalized_ids if group_id != 0]
    if real_group_ids:
        conditions.append(TelegramSession.group_id.in_(real_group_ids))
    if 0 in normalized_ids:
        conditions.append(TelegramSession.group_id.is_(None))
    if not conditions:
        return

    from sqlalchemy import or_

    sessions = db.scalars(select(TelegramSession).where(or_(*conditions), TelegramSession.owner_id == owner_id)).all()
    for session in sessions:
        session.kf_id = agent_id


def _apply_bindings(db: Session, agent_id: int, payload: SupportAgentPayload, owner_id: int) -> None:
    if payload.group_ids is not None:
        _bind_groups(db, agent_id, payload.group_ids, owner_id)
        return
    if payload.session_ids is not None:
        _bind_sessions(db, agent_id, payload.session_ids, owner_id)


def _serialize_agent(agent: SupportAgent) -> dict[str, Any]:
    sessions = sorted(agent.sessions, key=lambda item: item.id)
    return {
        "id": agent.id,
        "name": agent.name,
        "remark": agent.remark,
        "color": agent.color,
        "status": agent.status,
        "session_count": len(sessions),
        "sessions": [
            {
                "id": session.id,
                "username": session.username,
                "phone": session.phone,
                "session_name": session.session_name,
                "group_id": session.group_id,
                "group_name": session.group.name if session.group else None,
                "status": session.status.value if hasattr(session.status, "value") else session.status,
            }
            for session in sessions
        ],
        "created_at": agent.created_at.isoformat() if agent.created_at else None,
        "updated_at": agent.updated_at.isoformat() if agent.updated_at else None,
    }
