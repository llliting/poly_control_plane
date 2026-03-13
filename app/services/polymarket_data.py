from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request
from datetime import UTC, datetime

from app.core.config import settings

_CACHE: dict[tuple[str, str], tuple[float, dict]] = {}
_CACHE_TTL_SECS = 10.0


def _get_json(url: str, timeout: float = 4.0) -> dict | list:
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _get_json_or_default(url: str, default: dict | list, timeout: float = 4.0) -> dict | list:
    try:
        return _get_json(url, timeout=timeout)
    except Exception:
        return default


def _cached(key: tuple[str, str], loader) -> dict:
    now = time.time()
    cached = _CACHE.get(key)
    if cached and now - cached[0] < _CACHE_TTL_SECS:
        return cached[1]
    value = loader()
    _CACHE[key] = (now, value)
    return value


def _iso_date_to_ts(date_str: str, end_of_day: bool = False) -> int:
    hour = 23 if end_of_day else 0
    minute = 59 if end_of_day else 0
    second = 59 if end_of_day else 0
    dt = datetime.fromisoformat(date_str).replace(
        tzinfo=UTC,
        hour=hour,
        minute=minute,
        second=second,
        microsecond=0,
    )
    return int(dt.timestamp())


def fetch_wallet_summary(wallet: str, from_date: str, to_date: str) -> dict | None:
    wallet = (wallet or "").strip()
    if not wallet:
        return None

    base = settings.polymarket_data_host.rstrip("/")
    key = (wallet, f"{from_date}:{to_date}")

    def _load() -> dict:
        value_url = f"{base}/value?user={urllib.parse.quote(wallet)}"
        positions_url = (
            f"{base}/positions?user={urllib.parse.quote(wallet)}"
            "&limit=200&sizeThreshold=0"
        )
        activity_params = urllib.parse.urlencode(
            {
                "user": wallet,
                "type": "TRADE",
                "limit": 200,
                "start": _iso_date_to_ts(from_date, end_of_day=False),
                "end": _iso_date_to_ts(to_date, end_of_day=True),
            }
        )
        activity_url = f"{base}/activity?{activity_params}"

        value_raw = _get_json(value_url)
        positions_raw = _get_json_or_default(positions_url, [])
        activity_raw = _get_json_or_default(activity_url, [])

        positions = positions_raw if isinstance(positions_raw, list) else []
        activity = activity_raw if isinstance(activity_raw, list) else []
        if isinstance(value_raw, list):
            value_row = value_raw[0] if value_raw else {}
        elif isinstance(value_raw, dict):
            value_row = value_raw
        else:
            value_row = {}

        current_value = float((value_row or {}).get("value") or 0.0)

        open_position_count = 0
        redeemable_value = 0.0
        positions_value = 0.0
        realized_pnl = 0.0
        unrealized_pnl = 0.0
        for row in positions:
            size = float(row.get("size") or 0.0)
            if abs(size) > 0:
                open_position_count += 1
            positions_value += float(row.get("currentValue") or 0.0)
            if bool(row.get("redeemable")):
                redeemable_value += float(row.get("currentValue") or 0.0)
            realized_pnl += float(row.get("realizedPnl") or 0.0)
            unrealized_pnl += float(row.get("curPnl") or 0.0)

        cash_value = current_value - positions_value
        if abs(cash_value) < 1e-9:
            cash_value = 0.0

        activity_count = len(activity)
        return {
            "wallet": wallet,
            "current_value_usdc": current_value,
            "cash_usdc": cash_value,
            "positions_value_usdc": positions_value,
            "redeemable_usdc": redeemable_value,
            "open_position_count": open_position_count,
            "positions_realized_pnl_usdc": realized_pnl,
            "positions_unrealized_pnl_usdc": unrealized_pnl,
            "trade_activity_count": activity_count,
        }

    try:
        return _cached(key, _load)
    except Exception:
        return None
