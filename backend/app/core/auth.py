import base64
import hashlib
import hmac
import json
import os
import time
from typing import Any

from fastapi import Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.user import User

SECRET = os.environ.get("AUTH_SECRET", "change-this-auth-secret")
TOKEN_TTL_SECONDS = 60 * 60 * 24 * 7
MENU_PERMISSIONS = (
    "dashboard",
    "sessions",
    "messages",
    "customers",
    "customer_profiles",
    "materials",
    "tasks",
    "proxies",
    "usage_docs",
)
DEFAULT_MENU_PERMISSIONS = ("messages", "materials")


def normalize_menu_permissions(value: Any) -> list[str]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (TypeError, ValueError):
            value = []
    if not isinstance(value, (list, tuple, set)):
        return []
    selected = set(value)
    return [permission for permission in MENU_PERMISSIONS if permission in selected]


def get_user_menu_permissions(user: User) -> list[str]:
    if user.role == "root":
        return list(MENU_PERMISSIONS)
    return normalize_menu_permissions(user.menu_permissions)


def require_menu_access(permission: str):
    return require_any_menu_access(permission)


def require_any_menu_access(*permissions: str):
    unknown = set(permissions) - set(MENU_PERMISSIONS)
    if unknown:
        raise ValueError(f"Unknown menu permission: {', '.join(sorted(unknown))}")

    def dependency(user: User = Depends(get_current_user)) -> User:
        allowed = set(get_user_menu_permissions(user))
        if user.role != "root" and not allowed.intersection(permissions):
            raise HTTPException(status_code=404, detail="Not Found")
        return user

    return dependency


def hash_password(password: str, salt: str | None = None) -> str:
    salt = salt or os.urandom(16).hex()
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 120000).hex()
    return f"pbkdf2_sha256${salt}${digest}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, salt, digest = stored.split("$", 2)
    except ValueError:
        return False
    return hmac.compare_digest(hash_password(password, salt).split("$", 2)[2], digest)


def create_token(user: User) -> str:
    payload = {
        "sub": user.id,
        "username": user.username,
        "role": user.role,
        "exp": int(time.time()) + TOKEN_TTL_SECONDS,
    }
    body = _b64(json.dumps(payload, separators=(",", ":")).encode())
    signature = _sign(body)
    return f"{body}.{signature}"


def decode_token(token: str) -> dict[str, Any]:
    try:
        body, signature = token.split(".", 1)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail="Invalid token") from exc
    if not hmac.compare_digest(_sign(body), signature):
        raise HTTPException(status_code=401, detail="Invalid token")
    payload = json.loads(base64.urlsafe_b64decode(_pad(body)).decode())
    if int(payload.get("exp") or 0) < int(time.time()):
        raise HTTPException(status_code=401, detail="Token expired")
    return payload


def get_current_user(authorization: str | None = Header(None), db: Session = Depends(get_db)) -> User:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")
    payload = decode_token(authorization.removeprefix("Bearer ").strip())
    user = db.get(User, int(payload["sub"]))
    if not user or user.status != "active":
        raise HTTPException(status_code=401, detail="User disabled")
    return user


def require_root(user: User = Depends(get_current_user)) -> User:
    if user.role != "root":
        raise HTTPException(status_code=403, detail="Root permission required")
    return user


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode().rstrip("=")


def _pad(value: str) -> bytes:
    return (value + "=" * (-len(value) % 4)).encode()


def _sign(body: str) -> str:
    return _b64(hmac.new(SECRET.encode(), body.encode(), hashlib.sha256).digest())


def ensure_default_users(db: Session) -> tuple[User, User]:
    root = db.scalar(select(User).where(User.username == "root"))
    if not root:
        root = User(username="root", password_hash=hash_password("root"), role="root")
        db.add(root)
        db.flush()
    test = db.scalar(select(User).where(User.username == "test"))
    if not test:
        test = User(
            username="test",
            password_hash=hash_password("test"),
            role="user",
            menu_permissions=json.dumps(DEFAULT_MENU_PERMISSIONS),
        )
        db.add(test)
        db.flush()
    db.commit()
    db.refresh(root)
    db.refresh(test)
    return root, test
