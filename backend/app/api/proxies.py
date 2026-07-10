from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.services.proxy_service import proxy_service


class ProxyPayload(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    scheme: str = Field(pattern="^(http|https|socks4|socks5)$")
    host: str = Field(min_length=1, max_length=255)
    port: int = Field(ge=1, le=65535)
    username: str | None = Field(default=None, max_length=150)
    password: str | None = Field(default=None, max_length=255)
    color: str = Field(default="blue", pattern="^(red|orange|yellow|green|blue|geekblue|purple)$")
    is_active: bool = False
    group_ids: list[int] | None = None


router = APIRouter(prefix="/proxies", tags=["proxies"])


@router.get("")
def list_proxies(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> list[dict[str, Any]]:
    return [proxy_service.serialize_proxy(item) for item in proxy_service.list_proxies(db, user.id)]


@router.post("")
def create_proxy(payload: ProxyPayload, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict[str, Any]:
    proxy = proxy_service.create_proxy(db, payload.model_dump(), user.id)
    return proxy_service.serialize_proxy(proxy)


@router.put("/{proxy_id}")
def update_proxy(proxy_id: int, payload: ProxyPayload, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict[str, Any]:
    try:
        proxy = proxy_service.update_proxy(db, proxy_id, payload.model_dump(), user.id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return proxy_service.serialize_proxy(proxy)


@router.delete("/{proxy_id}")
def delete_proxy(proxy_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict[str, bool]:
    try:
        proxy_service.delete_proxy(db, proxy_id, user.id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"ok": True}


@router.post("/{proxy_id}/activate")
def activate_proxy(proxy_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict[str, Any]:
    try:
        proxy = proxy_service.activate_proxy(db, proxy_id, user.id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return proxy_service.serialize_proxy(proxy)


@router.post("/{proxy_id}/test")
def test_proxy(proxy_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict[str, Any]:
    try:
        proxy = proxy_service.test_proxy(db, proxy_id, user.id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return proxy_service.serialize_proxy(proxy)
