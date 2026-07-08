from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.session import GroupCreate, MoveSessions, SessionCreate, SessionUpdate
from app.services.session_service import session_service
from app.services.websocket_manager import session_ws_manager

router = APIRouter(prefix="/sessions", tags=["sessions"])
ws_router = APIRouter(tags=["sessions-ws"])


@router.get("")
def list_sessions(group_id: int | None = None, db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    return [session_service.serialize_session(item) for item in session_service.list_sessions(db, group_id)]


@router.post("")
def create_session(payload: SessionCreate, db: Session = Depends(get_db)) -> dict[str, Any]:
    return session_service.serialize_session(session_service.create_session(db, payload.model_dump()))


@router.put("/{session_id}")
async def update_session(session_id: int, payload: SessionUpdate, db: Session = Depends(get_db)) -> dict[str, Any]:
    try:
        session = await session_service.update_session(db, session_id, payload.model_dump(exclude_unset=True))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return session_service.serialize_session(session)


@router.delete("/{session_id}")
async def delete_session(session_id: int, db: Session = Depends(get_db)) -> dict[str, bool]:
    try:
        await session_service.delete_session(db, session_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"ok": True}


@router.post("/import")
async def import_sessions(file: UploadFile = File(...), db: Session = Depends(get_db)) -> dict[str, int]:
    return await session_service.import_sessions(db, file)


@router.get("/groups")
def list_groups(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    return [
        {
            "id": group.id,
            "name": group.name,
            "description": group.description,
            "created_at": group.created_at.isoformat(),
        }
        for group in session_service.list_groups(db)
    ]


@router.post("/groups")
def create_group(payload: GroupCreate, db: Session = Depends(get_db)) -> dict[str, Any]:
    group = session_service.create_group(db, payload.name, payload.description)
    return {"id": group.id, "name": group.name, "description": group.description, "created_at": group.created_at.isoformat()}


@router.post("/move")
async def move_sessions(payload: MoveSessions, db: Session = Depends(get_db)) -> dict[str, int]:
    moved = await session_service.move_sessions(db, payload.session_ids, payload.group_id)
    return {"moved": moved}


@router.post("/health-check")
async def health_check(db: Session = Depends(get_db)) -> dict[str, int]:
    return await session_service.health_check_once(db)


@router.get("/logs")
def list_logs(session_id: int | None = None, limit: int = 100, db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    logs = session_service.list_logs(db, session_id, limit)
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


@ws_router.websocket("/ws/sessions/{session_id}")
async def session_websocket(websocket: WebSocket, session_id: str):
    key = "*" if session_id in {"all", "*", "0"} else session_id
    await session_ws_manager.connect(key, websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        await session_ws_manager.disconnect(key, websocket)
