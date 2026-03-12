from fastapi import APIRouter, HTTPException, Query

from app.services.mock_data import DECISIONS, RUNTIME_ROWS, get_service_or_none, get_services
from app.services.repository import (
    get_service_detail_from_db,
    list_decisions_from_db,
    list_runtime_signals_from_db,
    list_services_from_db,
)

router = APIRouter()


@router.get("/services")
def services() -> dict:
    try:
        rows = list_services_from_db()
        if rows is not None:
            return {"items": rows}
    except Exception:
        # Keep API available while DB wiring is in progress.
        pass
    return {"items": get_services()}


@router.get("/services/{service_key}")
def service_detail(service_key: str) -> dict:
    try:
        data = get_service_detail_from_db(service_key)
        if data is not None:
            return data
    except Exception:
        pass

    service = get_service_or_none(service_key)
    if not service:
        raise HTTPException(status_code=404, detail="service not found")
    return {
        "service": service,
        "health": service["health"],
        "controls": {
            "can_start": service["status"] == "stopped",
            "can_stop": service["status"] in {"healthy", "degraded"},
            "allowed_actions": ["start", "stop", "build", "restart", "redeploy"],
        },
    }


@router.get("/services/{service_key}/decisions")
def service_decisions(service_key: str, limit: int = Query(default=50, ge=1, le=500)) -> dict:
    try:
        items = list_decisions_from_db(service_key=service_key, limit=limit)
        if items is not None:
            return {"items": items}
    except Exception:
        pass

    items = DECISIONS.get(service_key, [])
    return {"items": items[:limit]}


@router.get("/services/{service_key}/runtime-signals")
def runtime_signals(service_key: str, limit: int = Query(default=50, ge=1, le=500)) -> dict:
    try:
        items = list_runtime_signals_from_db(service_key=service_key, limit=limit)
        if items is not None:
            return {"items": items}
    except Exception:
        pass

    items = RUNTIME_ROWS.get(service_key, [])
    return {"items": items[:limit]}
