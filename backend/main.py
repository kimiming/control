from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from app.api import auth, customer_profiles, customers, dashboard, materials, messages, proxies, sessions, support_agents, tasks
from app.core.config import get_settings
from app.core.database import Base, engine
from app.core.migrations import run_lightweight_migrations
from app.models import Customer, CustomerProfile, MarketingTask, Material, MaterialGroup, MaterialUsageLog, Message, ProxyConfig, SessionGroup, SessionLog, SessionTaskLog, SupportAgent, TaskOutbox, TaskTarget, TelegramSession, User

settings = get_settings()

app = FastAPI(title=settings.app_name)
app.mount("/static", StaticFiles(directory="static"), name="static")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(sessions.router, prefix=settings.api_prefix)
app.include_router(auth.router, prefix=settings.api_prefix)
app.include_router(messages.router, prefix=settings.api_prefix)
app.include_router(tasks.router, prefix=settings.api_prefix)
app.include_router(materials.router, prefix=settings.api_prefix)
app.include_router(customers.router, prefix=settings.api_prefix)
app.include_router(customer_profiles.router, prefix=settings.api_prefix)
app.include_router(support_agents.router, prefix=settings.api_prefix)
app.include_router(proxies.router, prefix=settings.api_prefix)
app.include_router(dashboard.router, prefix=settings.api_prefix)
app.include_router(sessions.ws_router)


@app.on_event("startup")
async def startup() -> None:
    Base.metadata.create_all(bind=engine)
    run_lightweight_migrations()


@app.on_event("shutdown")
async def shutdown() -> None:
    pass


@app.get("/health")
def health():
    return {"ok": True}
