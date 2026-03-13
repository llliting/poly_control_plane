from __future__ import annotations

from collections import defaultdict, deque
from datetime import UTC, datetime
from threading import Lock

_MAX_HISTORY = 200
_lock = Lock()
_latest_by_service: dict[str, dict] = {}
_history_by_service: dict[str, deque[dict]] = defaultdict(lambda: deque(maxlen=_MAX_HISTORY))


def _iso_now() -> str:
    return datetime.now(tz=UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def upsert_runtime_snapshot(payload: dict) -> dict:
    service_key = str(payload.get("service_key") or "").strip()
    if not service_key:
        raise ValueError("service_key is required")

    captured_at = str(payload.get("captured_at") or _iso_now())
    snapshot = {
        "service_key": service_key,
        "captured_at": captured_at,
        "status": payload.get("status") or "healthy",
        "signal": payload.get("signal"),
        "p_up": payload.get("p_up"),
        "edge": payload.get("edge"),
        "traded": payload.get("traded"),
        "portfolio_usdc": payload.get("portfolio_usdc"),
        "position_usdc": payload.get("position_usdc"),
        "cash_usdc": payload.get("cash_usdc"),
        "binance_price": payload.get("binance_price"),
        "chainlink_price": payload.get("chainlink_price"),
        "pm_mid": payload.get("pm_mid"),
        "pm_bid": payload.get("pm_bid"),
        "pm_ask": payload.get("pm_ask"),
        "cl_bin_spread": payload.get("cl_bin_spread"),
        "bucket_seconds_left": payload.get("bucket_seconds_left"),
        "ingest_lag_ms": payload.get("ingest_lag_ms"),
        "streak_hits": payload.get("streak_hits"),
        "streak_target": payload.get("streak_target"),
    }

    with _lock:
        _latest_by_service[service_key] = snapshot
        _history_by_service[service_key].appendleft(snapshot)
    return snapshot


def get_latest_runtime_snapshot(service_key: str) -> dict | None:
    with _lock:
        item = _latest_by_service.get(service_key)
        return dict(item) if item else None


def list_runtime_snapshots(service_key: str, limit: int = 50) -> list[dict]:
    with _lock:
        rows = list(_history_by_service.get(service_key, ()))[:limit]
    return [dict(row) for row in rows]


def overlay_service_row(row: dict) -> dict:
    service_key = str(row.get("service_key") or row.get("name") or "").strip()
    live = get_latest_runtime_snapshot(service_key)
    if not live:
        return row

    out = dict(row)
    if live.get("status"):
        out["status"] = live["status"]
    if live.get("signal") is not None:
        out["signal"] = live["signal"]
    if live.get("p_up") is not None:
        out["p_up"] = float(live["p_up"] or 0.0)
    if live.get("edge") is not None:
        out["edge"] = float(live["edge"] or 0.0)
    if live.get("traded") is not None:
        out["traded"] = bool(live["traded"])
    if live.get("portfolio_usdc") is not None:
        out["portfolio_usdc"] = float(live["portfolio_usdc"] or 0.0)
    if live.get("position_usdc") is not None:
        out["position_usdc"] = float(live["position_usdc"] or 0.0)
    if live.get("cash_usdc") is not None:
        out["cash_usdc"] = float(live["cash_usdc"] or 0.0)
    if live.get("captured_at"):
        try:
            ts = datetime.fromisoformat(str(live["captured_at"]).replace("Z", "+00:00"))
            age = max(0, int((datetime.now(tz=UTC) - ts.astimezone(UTC)).total_seconds()))
            out["heartbeat_age_sec"] = age
        except Exception:
            pass
    return out


def overlay_service_detail(data: dict) -> dict:
    service = data.get("service") or {}
    health = data.get("health") or {}
    out = {
        "service": overlay_service_row(service),
        "health": dict(health),
        "controls": dict(data.get("controls") or {}),
    }
    live = get_latest_runtime_snapshot(str(service.get("service_key") or "").strip())
    if live and live.get("ingest_lag_ms") is not None:
        out["health"]["last_event_age_ms"] = int(live["ingest_lag_ms"] or 0)
    return out


def runtime_overview_money(service_keys: list[str]) -> dict | None:
    rows = [get_latest_runtime_snapshot(key) for key in service_keys if key]
    rows = [row for row in rows if row and row.get("portfolio_usdc") is not None]
    if len(rows) != 1:
        return None

    row = rows[0]
    return {
        "portfolio_value_usdc": round(float(row.get("portfolio_usdc") or 0.0), 4),
        "positions_value_usdc": round(float(row.get("position_usdc") or 0.0), 4),
        "cash_usdc": round(float(row.get("cash_usdc") or 0.0), 4),
    }
