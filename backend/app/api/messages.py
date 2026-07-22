from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.auth import get_current_user, require_menu_access
from app.core.database import get_db
from app.models.user import User
from app.services.message_service import message_service

router = APIRouter(prefix="/messages", tags=["messages"], dependencies=[Depends(require_menu_access("messages"))])


@router.get("")
def list_messages(page: int = 1, page_size: int = 50, session_id: int | None = None, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    messages = message_service.list_messages(db, page, min(page_size, 200), session_id, user.id)
    return [
        {
            "id": item.id,
            "session_id": item.session_id,
            "chat_id": item.chat_id,
            "sender": item.sender,
            "content": item.content,
            "created_at": item.created_at.isoformat(),
        }
        for item in messages
    ]
