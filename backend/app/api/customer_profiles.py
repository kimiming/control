from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.auth import get_current_user, require_any_menu_access
from app.core.database import get_db
from app.models.customer_profile import CustomerProfile
from app.models.user import User
from app.services.target_parser import parse_targets, validate_target_type


router = APIRouter(prefix="/customer-profiles", tags=["customer-profiles"], dependencies=[Depends(require_any_menu_access("customer_profiles", "tasks"))])


@router.get("")
def list_customer_profiles(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> list[dict[str, Any]]:
    profiles = db.scalars(select(CustomerProfile).where(CustomerProfile.owner_id == user.id).order_by(CustomerProfile.created_at.desc())).all()
    return [_serialize_profile(item) for item in profiles]


@router.get("/{profile_id}")
def get_customer_profile(profile_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict[str, Any]:
    profile = db.get(CustomerProfile, profile_id)
    if not profile or profile.owner_id != user.id:
        raise HTTPException(status_code=404, detail="客户资料不存在")
    return _serialize_profile(profile, include_content=True)


@router.post("")
async def create_customer_profile(
    name: str = Form(...),
    target_type: str = Form("phone"),
    remark: str | None = Form(None),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    content = (await file.read()).decode("utf-8-sig", errors="ignore")
    try:
        target_type = validate_target_type(target_type)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    targets = parse_targets(content, target_type)
    if not targets:
        label = "手机号" if target_type == "phone" else "用户名"
        raise HTTPException(status_code=400, detail=f"客户资料TXT里没有识别到{label}")
    profile = CustomerProfile(
        owner_id=user.id,
        name=name,
        target_type=target_type,
        remark=remark,
        content="\n".join(targets),
        total_count=len(targets),
    )
    db.add(profile)
    db.commit()
    db.refresh(profile)
    return _serialize_profile(profile, include_content=True)


@router.put("/{profile_id}")
async def update_customer_profile(
    profile_id: int,
    name: str = Form(...),
    target_type: str = Form("phone"),
    remark: str | None = Form(None),
    file: UploadFile | None = File(None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    profile = db.get(CustomerProfile, profile_id)
    if not profile or profile.owner_id != user.id:
        raise HTTPException(status_code=404, detail="客户资料不存在")
    profile.name = name
    profile.remark = remark
    try:
        target_type = validate_target_type(target_type)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    source_content = (await file.read()).decode("utf-8-sig", errors="ignore") if file else profile.content
    if file or target_type != (profile.target_type or "phone"):
        targets = parse_targets(source_content, target_type)
        if not targets:
            label = "手机号" if target_type == "phone" else "用户名"
            raise HTTPException(status_code=400, detail=f"客户资料TXT里没有识别到{label}")
        profile.content = "\n".join(targets)
        profile.total_count = len(targets)
    profile.target_type = target_type
    db.commit()
    db.refresh(profile)
    return _serialize_profile(profile, include_content=True)


@router.delete("/{profile_id}")
def delete_customer_profile(profile_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict[str, bool]:
    profile = db.get(CustomerProfile, profile_id)
    if not profile or profile.owner_id != user.id:
        raise HTTPException(status_code=404, detail="客户资料不存在")
    db.delete(profile)
    db.commit()
    return {"ok": True}


def _serialize_profile(profile: CustomerProfile, include_content: bool = False) -> dict[str, Any]:
    data = {
        "id": profile.id,
        "name": profile.name,
        "target_type": profile.target_type or "phone",
        "total_count": profile.total_count,
        "remark": profile.remark,
        "created_at": profile.created_at.isoformat() if profile.created_at else None,
        "updated_at": profile.updated_at.isoformat() if profile.updated_at else None,
    }
    if include_content:
        data["content"] = profile.content
    return data
