import re
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.database import get_db
from app.models.customer_profile import CustomerProfile
from app.models.user import User


router = APIRouter(prefix="/customer-profiles", tags=["customer-profiles"])


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
    remark: str | None = Form(None),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    content = (await file.read()).decode("utf-8-sig", errors="ignore")
    targets = _parse_targets(content)
    if not targets:
        raise HTTPException(status_code=400, detail="客户资料TXT里没有识别到手机号")
    profile = CustomerProfile(owner_id=user.id, name=name, remark=remark, content="\n".join(targets), total_count=len(targets))
    db.add(profile)
    db.commit()
    db.refresh(profile)
    return _serialize_profile(profile, include_content=True)


@router.put("/{profile_id}")
async def update_customer_profile(
    profile_id: int,
    name: str = Form(...),
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
    if file:
        content = (await file.read()).decode("utf-8-sig", errors="ignore")
        targets = _parse_targets(content)
        if not targets:
            raise HTTPException(status_code=400, detail="客户资料TXT里没有识别到手机号")
        profile.content = "\n".join(targets)
        profile.total_count = len(targets)
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


def _parse_targets(text: str) -> list[str]:
    targets: list[str] = []
    seen: set[str] = set()
    for line in text.splitlines():
        match = re.search(r"\+?\d[\d\s().-]{4,}\d", line)
        if not match:
            continue
        phone = re.sub(r"[\s().-]+", "", match.group(0))
        if phone and phone not in seen:
            seen.add(phone)
            targets.append(phone[:32])
    return targets


def _serialize_profile(profile: CustomerProfile, include_content: bool = False) -> dict[str, Any]:
    data = {
        "id": profile.id,
        "name": profile.name,
        "total_count": profile.total_count,
        "remark": profile.remark,
        "created_at": profile.created_at.isoformat() if profile.created_at else None,
        "updated_at": profile.updated_at.isoformat() if profile.updated_at else None,
    }
    if include_content:
        data["content"] = profile.content
    return data
