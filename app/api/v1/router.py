from fastapi import APIRouter

from app.api.v1.endpoints import actions, ingest, logs, market, overview, services, session, trades

router = APIRouter()
router.include_router(session.router, tags=["session"])
router.include_router(overview.router, tags=["overview"])
router.include_router(services.router, tags=["services"])
router.include_router(market.router, tags=["market"])
router.include_router(trades.router, tags=["trades"])
router.include_router(logs.router, tags=["logs"])
router.include_router(actions.router, tags=["actions"])
router.include_router(ingest.router, tags=["ingest"])
