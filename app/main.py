from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.config import settings
from app.services import polymarket_poller
from app.services.action_executor import ActionExecutor

_action_executor: ActionExecutor | None = None


@asynccontextmanager
async def lifespan(_app: FastAPI):
    global _action_executor
    if settings.action_executor_enabled:
        _action_executor = ActionExecutor()
        _action_executor.start()
    if settings.polymarket_overview_wallet:
        polymarket_poller.start()
    try:
        yield
    finally:
        polymarket_poller.stop()
        if _action_executor is not None:
            _action_executor.stop()
            _action_executor = None


app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8081", "http://127.0.0.1:8081"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(api_router, prefix=settings.api_prefix)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}
