import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.background import BackgroundTask

from app.core.auth import decode_token, get_current_user, require_any_menu_access
from app.core.database import SessionLocal, get_db
from app.models.user import User
from app.models.session import TelegramSession
from app.schemas.session import GroupCreate, MoveSessions, MoveSessionsToAgent, MoveSessionsToProxy, SessionCreate, SessionIds, SessionUpdate
from app.services.session_service import session_service
from app.services.session_command_bus import SessionCommandError, session_command_bus
from app.services.proxy_service import proxy_service
from app.services.websocket_manager import session_ws_manager
from app.core.cache import redis_client

router = APIRouter(prefix="/sessions", tags=["sessions"], dependencies=[Depends(require_any_menu_access("sessions", "customers", "tasks", "proxies"))])
ws_router = APIRouter(tags=["sessions-ws"])


async def _serialize_with_runtime(session: Any) -> dict[str, Any]:
    value = await redis_client.get(f"telegram:session:runtime:{session.id}")
    try:
        runtime = json.loads(value) if value else None
    except json.JSONDecodeError:
        runtime = None
    return session_service.serialize_session(session, runtime, include_runtime=True)


@router.get("")
async def list_sessions(
    group_id: int | None = None,
    kf_id: int | None = None,
    status: str | None = None,
    health_status: str | None = None,
    bidirectional_status: str | None = None,
    keyword: str | None = None,
    page: int = 1,
    page_size: int = 20,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    page = max(page, 1)
    page_size = min(max(page_size, 10), 100)
    sessions, total = session_service.list_sessions(
        db,
        group_id=group_id,
        kf_id=kf_id,
        status=status,
        health_status=health_status,
        keyword=keyword,
        owner_id=user.id,
        bidirectional_status=bidirectional_status,
        page=page,
        page_size=page_size,
    )
    values = await redis_client.mget(*[f"telegram:session:runtime:{item.id}" for item in sessions]) if sessions else []
    runtimes = []
    for value in values:
        try:
            runtimes.append(json.loads(value) if value else None)
        except json.JSONDecodeError:
            runtimes.append(None)
    session_ids = [item.id for item in sessions]
    sent_count_keys = [f"session:sent-count:{session_id}" for session_id in session_ids]
    cached_counts = await redis_client.mget(*sent_count_keys) if sent_count_keys else []
    sent_counts: dict[int, int] = {}
    missing_ids: list[int] = []
    for session_id, cached in zip(session_ids, cached_counts):
        if cached is None:
            missing_ids.append(session_id)
        else:
            sent_counts[session_id] = int(cached)
    if missing_ids:
        fresh_counts = session_service.count_sent_messages_batch(db, missing_ids)
        pipeline = redis_client.pipeline()
        for session_id in missing_ids:
            count = fresh_counts.get(session_id, 0)
            sent_counts[session_id] = count
            pipeline.set(f"session:sent-count:{session_id}", count, ex=30)
        await pipeline.execute()
    proxy_map = proxy_service.get_proxy_map_for_sessions(db, sessions, require_active=False)
    items = [
        session_service.serialize_session(
            item,
            runtime,
            include_runtime=True,
            proxy=proxy_map.get(item.id),
            sent_count=sent_counts.get(item.id, 0),
            resolve_related=False,
        )
        for item, runtime in zip(sessions, runtimes)
    ]
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@router.get("/runtime")
async def list_session_runtime(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[dict[str, Any]]:
    """Return only volatile worker heartbeats for inexpensive UI polling."""
    session_rows = list(db.execute(
        select(
            TelegramSession.id,
            TelegramSession.status,
            TelegramSession.bidirectional_status,
            TelegramSession.contact_count,
            TelegramSession.contact_scan_status,
            TelegramSession.contact_scan_detail,
        )
        .where(TelegramSession.owner_id == user.id)
    ).all())
    if not session_rows:
        return []
    session_ids = [int(row.id) for row in session_rows]
    values = await redis_client.mget(*[f"telegram:session:runtime:{session_id}" for session_id in session_ids])
    result: list[dict[str, Any]] = []
    for row, value in zip(session_rows, values):
        try:
            runtime = json.loads(value) if value else {}
        except json.JSONDecodeError:
            runtime = {}
        result.append({
            "id": int(row.id),
            "status": row.status.value if hasattr(row.status, "value") else str(row.status),
            "bidirectional_status": row.bidirectional_status or "unchecked",
            "contact_count": row.contact_count,
            "contact_scan_status": row.contact_scan_status or "idle",
            "contact_scan_detail": row.contact_scan_detail,
            "runtime_status": runtime.get("status", "offline"),
            "runtime_worker": runtime.get("worker"),
            "runtime_last_heartbeat": runtime.get("last_heartbeat"),
        })
    return result


@router.post("")
async def create_session(payload: SessionCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict[str, Any]:
    return await _serialize_with_runtime(session_service.create_session(db, payload.model_dump(), user.id))


@router.put("/{session_id}")
async def update_session(session_id: int, payload: SessionUpdate, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict[str, Any]:
    try:
        session = await session_service.update_session(db, session_id, payload.model_dump(exclude_unset=True), user.id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return await _serialize_with_runtime(session)


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


def _session_export_response(
    db: Session,
    user: User,
    session_ids: list[int] | None,
    scope: str,
) -> FileResponse:
    try:
        archive_path, summary = session_service.export_session_files(db, user.id, session_ids)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    filename = f"tg_sessions_{scope}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
    return FileResponse(
        archive_path,
        media_type="application/zip",
        filename=filename,
        headers={
            "X-Session-Requested": str(summary["requested"]),
            "X-Session-Found": str(summary["found"]),
            "X-Session-Exported": str(summary["exported"]),
            "X-Session-Missing": str(summary["missing"]),
        },
        background=BackgroundTask(Path(archive_path).unlink, missing_ok=True),
    )


@router.get("/export")
def export_all_sessions(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> FileResponse:
    return _session_export_response(db, user, None, "all")


@router.post("/export")
def export_selected_sessions(payload: SessionIds, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> FileResponse:
    return _session_export_response(db, user, payload.session_ids, "selected")


@router.get("/groups")
def list_groups(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> list[dict[str, Any]]:
    return [
        {
            "id": group.id,
            "name": group.name,
            "description": group.description,
            "color": group.color,
            "session_count": len(group.sessions),
            "created_at": group.created_at.isoformat(),
        }
        for group in session_service.list_groups(db, user.id)
    ]


@router.post("/groups")
def create_group(payload: GroupCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict[str, Any]:
    group = session_service.create_group(db, payload.name, payload.description, payload.color, user.id)
    return {"id": group.id, "name": group.name, "description": group.description, "color": group.color, "created_at": group.created_at.isoformat()}


@router.put("/groups/{group_id}")
def update_group(group_id: int, payload: GroupCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict[str, Any]:
    try:
        group = session_service.update_group(db, group_id, payload.name, payload.description, payload.color, user.id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"id": group.id, "name": group.name, "description": group.description, "color": group.color, "created_at": group.created_at.isoformat()}


@router.delete("/groups/{group_id}")
def delete_group(group_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict[str, bool]:
    try:
        session_service.delete_group(db, group_id, user.id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"ok": True}


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
async def connect_sessions(payload: SessionIds, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict[str, Any]:
    return await session_service.connect_sessions(db, payload.session_ids, user.id)


@router.post("/health-check")
async def health_check(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict[str, int]:
    return await session_service.health_check_once(db, user.id)


@router.post("/bidirectional-check")
async def batch_bidirectional_check(payload: SessionIds, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict[str, Any]:
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
    return await _serialize_with_runtime(session)


@router.post("/{session_id}/contacts/clear")
async def clear_contacts(session_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict[str, Any]:
    try:
        session = await session_service.clear_contacts(db, session_id, user.id)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return await _serialize_with_runtime(session)


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
        status_code = 404 if str(exc) == "Session not found" else 400
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc
    return await _serialize_with_runtime(session)


@router.get("/{session_id}/verification-code")
async def get_verification_code(
    session_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    sessions = session_service.get_sessions_by_ids(db, [session_id], user.id)
    if not sessions:
        raise HTTPException(status_code=404, detail="Session不存在")
    session = sessions[0]
    try:
        result = await session_command_bus.execute(session_id, "verification_code", timeout=30)
    except SessionCommandError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    received_at_value = result.get("received_at")
    received_at = None
    if received_at_value:
        try:
            received_at = datetime.fromisoformat(str(received_at_value).replace("Z", "+00:00"))
            if received_at.tzinfo is None:
                received_at = received_at.replace(tzinfo=timezone.utc)
        except ValueError:
            received_at = None
    age_seconds = max(0, int((datetime.now(timezone.utc) - received_at).total_seconds())) if received_at else None
    is_current = bool(result.get("code") and age_seconds is not None and age_seconds <= 300)
    return {
        "session_id": session.id,
        "session_name": session.session_name,
        "username": session.username,
        "phone": session.phone,
        "code": result.get("code"),
        "received_at": received_at_value,
        "age_seconds": age_seconds,
        "status": "current" if is_current else "future",
    }


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
    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=1008, reason="Not authenticated")
        return
    try:
        payload = decode_token(token)
        with SessionLocal() as db:
            user = db.get(User, int(payload["sub"]))
            if not user or user.status != "active":
                await websocket.close(code=1008, reason="User disabled")
                return
    except (HTTPException, KeyError, TypeError, ValueError):
        await websocket.close(code=1008, reason="Invalid token")
        return
    key = "*" if session_id in {"all", "*", "0"} else session_id
    await session_ws_manager.connect(key, websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        await session_ws_manager.disconnect(key, websocket)
