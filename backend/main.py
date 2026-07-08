import asyncio

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import messages, proxies, sessions, tasks
from app.core.config import get_settings
from app.core.database import Base, engine
from app.models import Message, SessionGroup, SessionLog, TelegramSession
from app.services.session_service import health_check_loop

settings = get_settings()

app = FastAPI(title=settings.app_name)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(sessions.router, prefix=settings.api_prefix)
app.include_router(messages.router, prefix=settings.api_prefix)
app.include_router(tasks.router, prefix=settings.api_prefix)
app.include_router(proxies.router, prefix=settings.api_prefix)
app.include_router(sessions.ws_router)


@app.on_event("startup")
async def startup() -> None:
    Base.metadata.create_all(bind=engine)
    asyncio.create_task(health_check_loop())


@app.get("/health")
def health():
    return {"ok": True}
