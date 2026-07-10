from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.services.task_service import task_service


router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.get("")
def list_tasks(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> list[dict[str, Any]]:
    return [task_service.serialize_task(item) for item in task_service.list_tasks(db, user.id)]


@router.get("/{task_id}")
def get_task(task_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict[str, Any]:
    try:
        task = task_service.get_task(db, task_id, user.id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return task_service.serialize_task(task)


@router.post("")
async def create_task(
    name: str = Form(...),
    content: str = Form(""),
    session_group_id: int | None = Form(None),
    messages_per_target: int = Form(3),
    content_material_id: int | None = Form(None),
    image_material_id: int | None = Form(None),
    contact_material_id: int | None = Form(None),
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
            owner_id=user.id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return task_service.serialize_task(task)


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
            owner_id=user.id,
        )
    except ValueError as exc:
        status_code = 404 if str(exc) == "Task not found" else 400
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc
    return task_service.serialize_task(task)


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
        task = await task_service.execute_task(db, task_id, user.id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return task_service.serialize_task(task)
