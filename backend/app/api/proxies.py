from fastapi import APIRouter

router = APIRouter(prefix="/proxies", tags=["proxies"])


@router.get("")
def list_proxies():
    return []
