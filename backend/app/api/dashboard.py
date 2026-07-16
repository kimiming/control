from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.services.dashboard_service import dashboard_service


router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/statistics")
def dashboard_statistics(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    return dashboard_service.get_statistics(db, user.id)
