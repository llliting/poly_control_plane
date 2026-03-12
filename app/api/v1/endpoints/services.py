from fastapi import APIRouter, HTTPException, Query

from app.services.mock_data import DECISIONS, RUNTIME_ROWS, get_service_or_none, get_services

router = APIRouter()


@router.get("/services")
def services() -> dict:
    return {"items": get_services()}


@router.get("/services/{service_key}")
def service_detail(service_key: str) -> dict:
    service = get_service_or_none(service_key)
    if not service:
        raise HTTPException(status_code=404, detail="service not found")
    return {
        "service": service,
        "health": service["health"],
        "controls": {
            "can_start": service["status"] == "stopped",
            "can_stop": service["status"] in {"healthy", "degraded"},
            "allowed_actions": ["start", "stop", "restart", "redeploy"],
        },
    }


@router.get("/services/{service_key}/decisions")
def service_decisions(service_key: str, limit: int = Query(default=50, ge=1, le=500)) -> dict:
    items = DECISIONS.get(service_key, [])
    return {"items": items[:limit]}


@router.get("/services/{service_key}/runtime-signals")
def runtime_signals(service_key: str, limit: int = Query(default=50, ge=1, le=500)) -> dict:
    items = RUNTIME_ROWS.get(service_key, [])
    return {"items": items[:limit]}

