from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.services.task_service import task_service
from app.services.task_queue import task_queue


router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.get("")
def list_tasks(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> list[dict[str, Any]]:
    return [task_service.serialize_task(item, db) for item in task_service.list_tasks(db, user.id)]


@router.get("/{task_id}")
def get_task(task_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict[str, Any]:
    try:
        task = task_service.get_task(db, task_id, user.id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return task_service.serialize_task(task, db)


@router.post("")
async def create_task(
    name: str = Form(...),
    content: str = Form(""),
    session_group_id: int | None = Form(None),
    messages_per_target: int = Form(3),
    content_material_id: int | None = Form(None),
    image_material_id: int | None = Form(None),
    contact_material_id: int | None = Form(None),
    send_type: str = Form("single"),
    material_group_id: int | None = Form(None),
    material_group_ids: str | None = Form(None),
    target_type: str = Form("phone"),
    target_source: str = Form("imported"),
    customer_profile_id: int | None = Form(None),
    targets_file: UploadFile | None = File(None),
    image: UploadFile | None = File(None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    try:
        task = await task_service.create_task(
            db,
            name,
            content,
            session_group_id,
            messages_per_target,
            targets_file,
            image,
            content_material_id,
            image_material_id,
            contact_material_id,
            customer_profile_id,
            send_type,
            material_group_id,
            material_group_ids,
            target_type,
            target_source,
            owner_id=user.id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return task_service.serialize_task(task, db)


@router.put("/{task_id}")
async def update_task(
    task_id: int,
    name: str = Form(...),
    content: str = Form(""),
    session_group_id: int | None = Form(None),
    messages_per_target: int = Form(3),
    content_material_id: int | None = Form(None),
    image_material_id: int | None = Form(None),
    contact_material_id: int | None = Form(None),
    send_type: str = Form("single"),
    material_group_id: int | None = Form(None),
    material_group_ids: str | None = Form(None),
    target_type: str = Form("phone"),
    target_source: str = Form("imported"),
    customer_profile_id: int | None = Form(None),
    targets_file: UploadFile | None = File(None),
    image: UploadFile | None = File(None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    try:
        task = await task_service.update_task(
            db,
            task_id,
            name,
            content,
            session_group_id,
            messages_per_target,
            targets_file,
            image,
            content_material_id,
            image_material_id,
            contact_material_id,
            customer_profile_id,
            send_type,
            material_group_id,
            material_group_ids,
            target_type,
            target_source,
            owner_id=user.id,
        )
    except ValueError as exc:
        status_code = 404 if str(exc) == "Task not found" else 400
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc
    return task_service.serialize_task(task, db)


@router.get("/{task_id}/logs")
def list_task_logs(
    task_id: int,
    page: int = 1,
    page_size: int = 50,
    status: str | None = None,
    keyword: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    try:
        return task_service.list_task_logs(db, task_id, page, page_size, status, keyword, user.id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{task_id}/remaining-targets")
def export_remaining_targets(
    task_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> StreamingResponse:
    try:
        task, targets = task_service.list_remaining_targets(db, task_id, user.id)
    except ValueError as exc:
        status_code = 404 if str(exc) == "Task not found" else 400
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc
    filename = quote(f"{task.name}-未发完客户资料.txt")
    def stream_targets():
        yield "\ufeff".encode("utf-8")
        for target in targets:
            yield f"{target}\n".encode("utf-8")

    return StreamingResponse(
        stream_targets(),
        media_type="text/plain; charset=utf-8",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{filename}",
            "X-Remaining-Count": str(len(targets)),
        },
    )


@router.delete("/{task_id}")
def delete_task(task_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict[str, bool]:
    try:
        task_service.delete_task(db, task_id, user.id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"ok": True}


@router.post("/{task_id}/execute")
async def execute_task(task_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict[str, Any]:
    try:
        task = await task_queue.enqueue_task(db, task_id, user.id)
    except ValueError as exc:
        status_code = 404 if str(exc) == "Task not found" else 400
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc
    return task_service.serialize_task(task, db)


@router.post("/{task_id}/pause")
async def pause_task(task_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict[str, Any]:
    from app.services.task_queue import task_queue
    try:
        task = task_service.pause_task(db, task_id, user.id)
        await task_queue.pause_task(task_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return task_service.serialize_task(task, db)


@router.post("/{task_id}/resume")
async def resume_task(task_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict[str, Any]:
    try:
        task = task_service.resume_task(db, task_id, user.id)
        await task_queue.publish_pending_outbox(task_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return task_service.serialize_task(task, db)


@router.post("/{task_id}/cancel")
async def cancel_task(task_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict[str, Any]:
    try:
        task = task_service.cancel_task(db, task_id, user.id)
        await task_queue.cancel_task(task_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return task_service.serialize_task(task, db)


@router.post("/{task_id}/retry-unsent")
async def retry_unsent(task_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict[str, Any]:
    try:
        task = await task_queue.enqueue_task(db, task_id, user.id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return task_service.serialize_task(task, db)


@router.post("/{task_id}/sessions/{session_id}/requeue")
async def requeue_session_job(task_id: int, session_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict[str, Any]:
    try:
        task = task_service.requeue_session_job(db, task_id, session_id, user.id)
        await task_queue.publish_pending_outbox(task_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return task_service.serialize_task(task, db)


@router.get("/{task_id}/active-sessions")
def active_task_sessions(task_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> list[dict[str, Any]]:
    try:
        return task_service.active_task_sessions(db, task_id, user.id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{task_id}/session-jobs")
def task_session_jobs(task_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> list[dict[str, Any]]:
    try:
        return task_service.task_session_jobs(db, task_id, user.id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
