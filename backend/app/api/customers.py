from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.services.customer_service import customer_service


class ReplyPayload(BaseModel):
    text: str | None = Field(default=None, max_length=5000)
    material_id: int | None = None


class FavoritePayload(BaseModel):
    is_favorite: bool


router = APIRouter(prefix="/customers", tags=["customers"])


@router.get("")
def list_customers(
    kf_id: int | None = None,
    keyword: str | None = None,
    reply_status: str | None = None,
    is_favorite: bool | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[dict[str, Any]]:
    return customer_service.list_customers(db, kf_id, keyword, reply_status, is_favorite, user.id)


@router.put("/{customer_id}/favorite")
def update_customer_favorite(customer_id: int, payload: FavoritePayload, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict[str, Any]:
    try:
        customer = customer_service.set_favorite(db, customer_id, payload.is_favorite, user.id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return customer_service.serialize_customer(db, customer)


@router.get("/{customer_id}/messages")
async def list_customer_messages(customer_id: int, limit: int = 100, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> list[dict[str, Any]]:
    try:
        messages = await customer_service.list_messages(db, customer_id, limit, user.id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return [customer_service.serialize_message(item) for item in messages]


@router.post("/{customer_id}/reply")
async def reply_customer(customer_id: int, payload: ReplyPayload, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict[str, Any]:
    try:
        customer = await customer_service.reply(db, customer_id, payload.text, payload.material_id, user.id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return customer_service.serialize_customer(db, customer)
