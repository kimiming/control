from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.services.material_service import material_service


class BatchDeletePayload(BaseModel):
    ids: list[int] = Field(min_length=1)


router = APIRouter(prefix="/materials", tags=["materials"])


@router.get("")
def list_materials(material_type: str | None = None, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> list[dict[str, Any]]:
    return [material_service.serialize_material(item) for item in material_service.list_materials(db, material_type, user.id)]


@router.get("/{material_id}")
def get_material(material_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict[str, Any]:
    try:
        material = material_service.get_material(db, material_id, user.id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return material_service.serialize_material(material)


@router.post("")
async def create_material(
    name: str = Form(...),
    material_type: str = Form(...),
    content: str | None = Form(None),
    priority: int = Form(0),
    remark: str | None = Form(None),
    file: UploadFile | None = File(None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    try:
        material = await material_service.create_material(
            db,
            {"name": name, "material_type": material_type, "content": content, "priority": priority, "remark": remark},
            file,
            user.id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return material_service.serialize_material(material)


@router.put("/{material_id}")
async def update_material(
    material_id: int,
    name: str = Form(...),
    material_type: str = Form(...),
    content: str | None = Form(None),
    priority: int = Form(0),
    remark: str | None = Form(None),
    file: UploadFile | None = File(None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    try:
        material = await material_service.update_material(
            db,
            material_id,
            {"name": name, "material_type": material_type, "content": content, "priority": priority, "remark": remark},
            file,
            user.id,
        )
    except ValueError as exc:
        status_code = 404 if str(exc) == "Material not found" else 400
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc
    return material_service.serialize_material(material)


@router.delete("/{material_id}")
def delete_material(material_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict[str, bool]:
    try:
        material_service.delete_material(db, material_id, user.id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"ok": True}


@router.post("/batch-delete")
def batch_delete(payload: BatchDeletePayload, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict[str, int]:
    return {"deleted": material_service.batch_delete(db, payload.ids, user.id)}
