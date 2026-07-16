from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.services.material_service import material_service


class BatchDeletePayload(BaseModel):
    ids: list[int] = Field(min_length=1)


class MaterialGroupPayload(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    color: str = Field(default="blue", pattern="^(red|orange|yellow|green|blue|geekblue|purple)$")
    remark: str | None = Field(default=None, max_length=500)


class BatchMovePayload(BaseModel):
    ids: list[int] = Field(min_length=1)
    group_id: int | None = None


router = APIRouter(prefix="/materials", tags=["materials"])


@router.get("")
def list_materials(
    material_type: str | None = Query(default=None, pattern="^(text|image|contact)$"),
    group_id: int | None = None,
    keyword: str | None = Query(default=None, max_length=200),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[dict[str, Any]]:
    materials = material_service.list_materials(
        db,
        material_type=material_type,
        owner_id=user.id,
        group_id=group_id,
        keyword=keyword,
    )
    return [material_service.serialize_material(item) for item in materials]


@router.get("/groups")
def list_material_groups(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> list[dict[str, Any]]:
    groups = material_service.list_groups(db, user.id)
    counts: dict[int, int] = {}
    type_counts: dict[int, dict[str, int]] = {}
    for material in material_service.list_materials(db, owner_id=user.id):
        if material.group_id is not None:
            counts[material.group_id] = counts.get(material.group_id, 0) + 1
            group_type_counts = type_counts.setdefault(material.group_id, {})
            group_type_counts[material.material_type] = group_type_counts.get(material.material_type, 0) + 1
    return [material_service.serialize_group(group, counts.get(group.id, 0), type_counts.get(group.id)) for group in groups]


@router.post("/groups")
def create_material_group(payload: MaterialGroupPayload, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict[str, Any]:
    try:
        group = material_service.create_group(db, payload.name, payload.remark, payload.color, user.id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return material_service.serialize_group(group)


@router.put("/groups/{group_id}")
def update_material_group(group_id: int, payload: MaterialGroupPayload, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict[str, Any]:
    try:
        group = material_service.update_group(db, group_id, payload.name, payload.remark, payload.color, user.id)
    except ValueError as exc:
        status_code = 404 if str(exc) == "Material group not found" else 400
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc
    return material_service.serialize_group(group)


@router.delete("/groups/{group_id}")
def delete_material_group(group_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict[str, bool]:
    try:
        material_service.delete_group(db, group_id, user.id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"ok": True}


@router.post("/batch-move")
def batch_move(payload: BatchMovePayload, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict[str, int]:
    try:
        moved = material_service.move_materials(db, payload.ids, payload.group_id, user.id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"moved": moved}


@router.post("/batch-delete")
def batch_delete(payload: BatchDeletePayload, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict[str, int]:
    return {"deleted": material_service.batch_delete(db, payload.ids, user.id)}


@router.post("/import-text")
async def import_text_materials(
    file: UploadFile = File(...),
    group_id: int | None = Form(None),
    delimiter: str | None = Form(default=None, max_length=100),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, int]:
    try:
        return await material_service.import_text_materials(
            db,
            file,
            group_id,
            user.id,
            delimiter,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/import-images")
async def import_image_materials(
    files: list[UploadFile] = File(...),
    group_id: int | None = Form(None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    try:
        return await material_service.import_image_materials(db, files, group_id, user.id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


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
    group_id: int | None = Form(None),
    remark: str | None = Form(None),
    file: UploadFile | None = File(None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    try:
        material = await material_service.create_material(
            db,
            {"name": name, "material_type": material_type, "content": content, "priority": priority, "remark": remark, "group_id": group_id},
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
    group_id: int | None = Form(None),
    remark: str | None = Form(None),
    file: UploadFile | None = File(None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    try:
        material = await material_service.update_material(
            db,
            material_id,
            {"name": name, "material_type": material_type, "content": content, "priority": priority, "remark": remark, "group_id": group_id},
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
