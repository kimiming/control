from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.auth import create_token, get_current_user, hash_password, require_root, verify_password
from app.core.database import get_db
from app.models.user import User


class LoginPayload(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=100)


class UserPayload(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=100)


class UserUpdatePayload(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    password: str | None = Field(default=None, max_length=100)
    status: str = Field(default="active", pattern="^(active|disabled)$")


class PasswordPayload(BaseModel):
    old_password: str = Field(min_length=1, max_length=100)
    new_password: str = Field(min_length=1, max_length=100)


router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login")
def login(payload: LoginPayload, db: Session = Depends(get_db)) -> dict[str, Any]:
    user = db.scalar(select(User).where(User.username == payload.username))
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    if user.status != "active":
        raise HTTPException(status_code=403, detail="用户已停用")
    return {"token": create_token(user), "user": serialize_user(user)}


@router.get("/me")
def me(user: User = Depends(get_current_user)) -> dict[str, Any]:
    return serialize_user(user)


@router.get("/users")
def list_users(_: User = Depends(require_root), db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    users = db.scalars(select(User).order_by(User.created_at.asc())).all()
    return [serialize_user(user) for user in users]


@router.post("/users")
def create_user(payload: UserPayload, _: User = Depends(require_root), db: Session = Depends(get_db)) -> dict[str, Any]:
    exists = db.scalar(select(User).where(User.username == payload.username))
    if exists:
        raise HTTPException(status_code=400, detail="用户名已存在")
    user = User(username=payload.username, password_hash=hash_password(payload.password), role="user")
    db.add(user)
    db.commit()
    db.refresh(user)
    return serialize_user(user)


@router.put("/users/{user_id}")
def update_user(user_id: int, payload: UserUpdatePayload, _: User = Depends(require_root), db: Session = Depends(get_db)) -> dict[str, Any]:
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    exists = db.scalar(select(User).where(User.username == payload.username, User.id != user_id))
    if exists:
        raise HTTPException(status_code=400, detail="用户名已存在")
    if user.role == "root" and payload.status != "active":
        root_count = db.scalar(select(func.count(User.id)).where(User.role == "root", User.status == "active")) or 0
        if root_count <= 1:
            raise HTTPException(status_code=400, detail="不能停用最后一个Root用户")
    user.username = payload.username
    user.status = payload.status
    if payload.password:
        user.password_hash = hash_password(payload.password)
    db.commit()
    db.refresh(user)
    return serialize_user(user)


@router.post("/change-password")
def change_password(payload: PasswordPayload, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict[str, bool]:
    if not verify_password(payload.old_password, user.password_hash):
        raise HTTPException(status_code=400, detail="原密码错误")
    user.password_hash = hash_password(payload.new_password)
    db.commit()
    return {"ok": True}


def serialize_user(user: User) -> dict[str, Any]:
    return {
        "id": user.id,
        "username": user.username,
        "role": user.role,
        "status": user.status,
        "created_at": user.created_at.isoformat() if user.created_at else None,
    }
