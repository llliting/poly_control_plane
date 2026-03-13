from fastapi import APIRouter, HTTPException, Query

from app.services.mock_data import DECISIONS, RUNTIME_ROWS, get_service_or_none, get_services
from app.services.action_executor import probe_service_state
from app.services.repository import (
    get_service_detail_from_db,
    list_decisions_from_db,
    list_runtime_signals_from_db,
    list_services_from_db,
)

router = APIRouter()


def _apply_probe_to_service_row(row: dict) -> dict:
    probe = probe_service_state(service_key=row["service_key"], runner_key=row.get("runner_key"))
    if not probe:
        return row
    out = dict(row)
    out["status"] = probe["status"]
    return out


def _apply_probe_to_detail(data: dict) -> dict:
    service = data["service"]
    probe = probe_service_state(service_key=service["service_key"], runner_key=service.get("runner_key"))
    if not probe:
        return data

    out = {
        "service": dict(service),
        "health": dict(data["health"]),
        "controls": dict(data["controls"]),
    }
    out["service"]["status"] = probe["status"]
    out["health"]["process_state"] = probe["process_state"]
    out["health"]["ready"] = probe["process_state"] == "running"
    out["controls"]["can_start"] = probe["can_start"]
    out["controls"]["can_stop"] = probe["can_stop"]
    if probe["build_available"] and "build" not in out["controls"].get("allowed_actions", []):
        out["controls"]["allowed_actions"] = [*out["controls"].get("allowed_actions", []), "build"]
    return out


@router.get("/services")
def services() -> dict:
    try:
        rows = list_services_from_db()
        if rows is not None:
            return {"items": [_apply_probe_to_service_row(row) for row in rows]}
    except Exception:
        # Keep API available while DB wiring is in progress.
        pass
    return {"items": get_services()}


@router.get("/services/{service_key}")
def service_detail(service_key: str) -> dict:
    try:
        data = get_service_detail_from_db(service_key)
        if data is not None:
            return _apply_probe_to_detail(data)
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
