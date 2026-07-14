import json
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.schemas.session import GroupCreate, MoveSessions, MoveSessionsToAgent, MoveSessionsToProxy, SessionCreate, SessionIds, SessionUpdate
from app.services.session_service import session_service
from app.services.proxy_service import proxy_service
from app.services.websocket_manager import session_ws_manager

router = APIRouter(prefix="/sessions", tags=["sessions"])
ws_router = APIRouter(tags=["sessions-ws"])


@router.get("")
def list_sessions(
    group_id: int | None = None,
    kf_id: int | None = None,
    status: str | None = None,
    health_status: str | None = None,
    keyword: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[dict[str, Any]]:
    sessions = session_service.list_sessions(db, group_id, kf_id, status, health_status, keyword, user.id)
    return [session_service.serialize_session(item) for item in sessions]


@router.post("")
def create_session(payload: SessionCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict[str, Any]:
    return session_service.serialize_session(session_service.create_session(db, payload.model_dump(), user.id))


@router.put("/{session_id}")
async def update_session(session_id: int, payload: SessionUpdate, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict[str, Any]:
    try:
        session = await session_service.update_session(db, session_id, payload.model_dump(exclude_unset=True), user.id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return session_service.serialize_session(session)


@router.delete("/{session_id}")
async def delete_session(session_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict[str, bool]:
    try:
        await session_service.delete_session(db, session_id, user.id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"ok": True}


@router.post("/import")
async def import_sessions(file: UploadFile = File(...), db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict[str, int]:
    return await session_service.import_sessions(db, file, user.id)


@router.get("/groups")
def list_groups(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> list[dict[str, Any]]:
    return [
        {
            "id": group.id,
            "name": group.name,
            "description": group.description,
            "color": group.color,
            "created_at": group.created_at.isoformat(),
        }
        for group in session_service.list_groups(db, user.id)
    ]


@router.post("/groups")
def create_group(payload: GroupCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict[str, Any]:
    group = session_service.create_group(db, payload.name, payload.description, payload.color, user.id)
    return {"id": group.id, "name": group.name, "description": group.description, "color": group.color, "created_at": group.created_at.isoformat()}


@router.post("/move")
async def move_sessions(payload: MoveSessions, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict[str, int]:
    moved = await session_service.move_sessions(db, payload.session_ids, payload.group_id, user.id)
    return {"moved": moved}


@router.post("/move-agent")
async def move_sessions_to_agent(payload: MoveSessionsToAgent, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict[str, int]:
    moved = await session_service.move_sessions_to_agent(db, payload.session_ids, payload.kf_id, user.id)
    return {"moved": moved}


@router.post("/move-proxy")
async def move_sessions_to_proxy(payload: MoveSessionsToProxy, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict[str, int]:
    try:
        moved = proxy_service.assign_sessions(db, payload.session_ids, payload.proxy_id, user.id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    sessions = session_service.get_sessions_by_ids(db, payload.session_ids, user.id)
    for session in sessions:
        await session_service.publish_status(session, "updated")
    return {"moved": moved}


@router.post("/disconnect")
async def disconnect_sessions(payload: SessionIds, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict[str, int]:
    disconnected = await session_service.disconnect_sessions(db, payload.session_ids, user.id)
    return {"disconnected": disconnected}


@router.post("/connect")
async def connect_sessions(payload: SessionIds, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict[str, int]:
    return await session_service.connect_sessions(db, payload.session_ids, user.id)


@router.post("/health-check")
async def health_check(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict[str, int]:
    return await session_service.health_check_once(db, user.id)


@router.post("/bidirectional-check")
async def batch_bidirectional_check(payload: SessionIds, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict[str, int]:
    return await session_service.check_bidirectional_statuses(db, payload.session_ids, user.id)


@router.post("/contacts/scan")
async def batch_scan_contacts(payload: SessionIds, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict[str, Any]:
    return await session_service.batch_contact_action(db, payload.session_ids, "scan", user.id)


@router.post("/contacts/clear")
async def batch_clear_contacts(payload: SessionIds, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict[str, Any]:
    return await session_service.batch_contact_action(db, payload.session_ids, "clear", user.id)


@router.post("/contacts/import")
async def batch_import_contacts(
    session_ids: str = Form(...),
    per_session_limit: int = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    try:
        raw_ids = json.loads(session_ids)
        if not isinstance(raw_ids, list):
            raise ValueError("Session参数格式错误")
        ids = [int(value) for value in raw_ids]
        if not ids:
            raise ValueError("请选择Session")
        phones = session_service.parse_contact_phones(await file.read())
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    try:
        result = await session_service.distribute_import_contacts(db, ids, phones, per_session_limit, user.id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    result["phone_count"] = len(phones)
    return result


@router.post("/{session_id}/contacts/scan")
async def scan_contacts(session_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict[str, Any]:
    try:
        session = await session_service.scan_contacts(db, session_id, user.id)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return session_service.serialize_session(session)


@router.post("/{session_id}/contacts/clear")
async def clear_contacts(session_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict[str, Any]:
    try:
        session = await session_service.clear_contacts(db, session_id, user.id)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return session_service.serialize_session(session)


@router.post("/{session_id}/contacts/import")
async def import_contacts(
    session_id: int,
    import_limit: int = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    try:
        phones = session_service.parse_contact_phones(await file.read())
        result = await session_service.distribute_import_contacts(db, [session_id], phones, import_limit, user.id)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    result["phone_count"] = len(phones)
    return result


@router.post("/{session_id}/bidirectional-check")
async def bidirectional_check(session_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict[str, Any]:
    try:
        session = await session_service.check_bidirectional_status(db, session_id, user.id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return session_service.serialize_session(session)


@router.get("/logs")
def list_logs(session_id: int | None = None, limit: int = 100, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> list[dict[str, Any]]:
    logs = session_service.list_logs(db, session_id, limit, user.id)
    return [
        {
            "id": item.id,
            "session_id": item.session_id,
            "action": item.action,
            "message": item.message,
            "operator": item.operator,
            "created_at": item.created_at.isoformat(),
        }
        for item in logs
    ]


@router.get("/{session_id}/task-logs")
def list_session_task_logs(session_id: int, limit: int = 100, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> list[dict[str, Any]]:
    if not session_service.get_sessions_by_ids(db, [session_id], user.id):
        raise HTTPException(status_code=404, detail="Session not found")
    logs = session_service.list_task_logs(db, session_id, limit)
    return [
        {
            "id": item.id,
            "session_id": item.session_id,
            "task_id": item.task_id,
            "task_name": item.task_name,
            "target_phone": item.target_phone,
            "status": item.status,
            "message": item.message,
            "created_at": item.created_at.isoformat(),
        }
        for item in logs
    ]


@ws_router.websocket("/ws/sessions/{session_id}")
async def session_websocket(websocket: WebSocket, session_id: str):
    key = "*" if session_id in {"all", "*", "0"} else session_id
    await session_ws_manager.connect(key, websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        await session_ws_manager.disconnect(key, websocket)
