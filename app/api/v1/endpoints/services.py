from fastapi import APIRouter, HTTPException, Query

from app.services.mock_data import DECISIONS, RUNTIME_ROWS, get_service_or_none, get_services
from app.services.action_executor import probe_service_state
from app.services.repository import (
    get_service_detail_from_db,
    list_decisions_from_db,
    list_runtime_signals_from_db,
    list_services_from_db,
)
from app.services.runtime_state import (
    list_runtime_snapshots,
    overlay_service_detail,
    overlay_service_row,
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
    commands = out["controls"].get("allowed_actions", [])
    if probe["build_available"] and "build" not in commands:
        commands = [*commands, "build"]
    if "redeem" not in commands:
        commands = [*commands, "redeem"]
    out["controls"]["allowed_actions"] = commands
    return out


@router.get("/services")
def services() -> dict:
    try:
        rows = list_services_from_db()
        if rows is not None:
            return {"items": [_apply_probe_to_service_row(overlay_service_row(row)) for row in rows]}
    except Exception:
        # Keep API available while DB wiring is in progress.
        pass
    return {"items": get_services()}


@router.get("/services/{service_key}")
def service_detail(service_key: str) -> dict:
    try:
        data = get_service_detail_from_db(service_key)
        if data is not None:
            return _apply_probe_to_detail(overlay_service_detail(data))
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
            "allowed_actions": ["start", "stop", "build", "redeem", "restart", "redeploy"],
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
    live_items = list_runtime_snapshots(service_key=service_key, limit=limit)
    if live_items:
        return {
            "items": [
                {
                    "ts": item["captured_at"],
                    "binance_price": float(item["binance_price"] or 0.0),
                    "chainlink_price": float(item["chainlink_price"] or 0.0),
                    "pm_mid": float(item["pm_mid"] or 0.0),
                    "pm_bid": float(item["pm_bid"] or 0.0),
                    "pm_ask": float(item["pm_ask"] or 0.0),
                    "cl_bin_spread": float(item["cl_bin_spread"] or 0.0),
                    "bucket_seconds_left": int(item["bucket_seconds_left"] or 0),
                    "ingest_lag_ms": int(item["ingest_lag_ms"] or 0),
                    "streak_hits": int(item["streak_hits"] or 0),
                    "streak_target": int(item["streak_target"] or 0),
                    "binance_price_change_5m": float(item["binance_price_change_5m"]) if item.get("binance_price_change_5m") is not None else None,
                    "danger_f_adx_3m": float(item["danger_f_adx_3m"]) if item.get("danger_f_adx_3m") is not None else None,
                    "danger_f_spread_3m": float(item["danger_f_spread_3m"]) if item.get("danger_f_spread_3m") is not None else None,
                    "danger_f_er_3m": float(item["danger_f_er_3m"]) if item.get("danger_f_er_3m") is not None else None,
                }
                for item in live_items
            ]
        }
    try:
        items = list_runtime_signals_from_db(service_key=service_key, limit=limit)
        if items is not None:
            return {"items": items}
    except Exception:
        pass

    items = RUNTIME_ROWS.get(service_key, [])
    return {"items": items[:limit]}
