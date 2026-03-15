"""Background poller that fetches portfolio, positions, and trades from the
Polymarket Data API on a recurring interval.  All data is cached in-memory
so that API endpoints can serve it instantly without waiting for external calls.

The poller does NOT require a private key — it uses the public Data API keyed
by wallet address (``POLYMARKET_OVERVIEW_WALLET`` in config).
"""

from __future__ import annotations

import json
import logging
import threading
import time
import urllib.parse
import urllib.request
from datetime import UTC, datetime

from app.core.config import settings

logger = logging.getLogger(__name__)

_POLL_INTERVAL_SECS = 30.0

# ---------------------------------------------------------------------------
# In-memory cache (thread-safe)
# ---------------------------------------------------------------------------

_lock = threading.Lock()
_wallet_summary: dict | None = None
_positions: list[dict] = []
_activity: list[dict] = []
_last_poll_at: float = 0.0


def get_wallet_summary() -> dict | None:
    with _lock:
        return dict(_wallet_summary) if _wallet_summary else None


def get_positions() -> list[dict]:
    with _lock:
        return list(_positions)


def get_open_positions() -> list[dict]:
    with _lock:
        return [p for p in _positions if abs(float(p.get("size") or 0)) > 0 and not p.get("redeemable")]


def get_activity() -> list[dict]:
    with _lock:
        return list(_activity)


def get_last_poll_at() -> float:
    with _lock:
        return _last_poll_at


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

def _get_json(url: str, timeout: float = 8.0) -> dict | list:
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _get_json_safe(url: str, default: dict | list | None = None, timeout: float = 8.0) -> dict | list:
    try:
        result = _get_json(url, timeout=timeout)
        return result
    except Exception as exc:
        print(f"[polymarket-poller] HTTP error: {url} — {exc}", flush=True)
        return default if default is not None else []


# ---------------------------------------------------------------------------
# Polling logic
# ---------------------------------------------------------------------------

def _build_position_row(raw: dict) -> dict:
    """Normalize a raw Polymarket position into a uniform dict."""
    size = float(raw.get("size") or 0)
    current_value = float(raw.get("currentValue") or 0)
    avg_price = float(raw.get("avgPrice") or 0)
    realized_pnl = float(raw.get("realizedPnl") or 0)
    cur_pnl = float(raw.get("curPnl") or 0)
    initial_value = float(raw.get("initialValue") or 0)
    cashout_value = float(raw.get("cashPnl") or 0)
    redeemable = bool(raw.get("redeemable"))

    # Determine status
    if redeemable:
        status = "redeemable"
    elif abs(size) > 0:
        status = "open"
    else:
        status = "closed"

    # Market info
    market = raw.get("market") or {}
    asset = raw.get("asset") or ""
    title = raw.get("title") or market.get("question") or ""
    slug = market.get("slug") or raw.get("slug") or ""
    outcome = raw.get("outcome") or ""
    end_date = market.get("endDate") or market.get("end_date_iso") or ""
    condition_id = raw.get("conditionId") or raw.get("condition_id") or ""

    return {
        "title": title,
        "slug": slug,
        "outcome": outcome,
        "asset": asset,
        "condition_id": condition_id,
        "size": size,
        "avg_price": avg_price,
        "current_value": current_value,
        "initial_value": initial_value,
        "realized_pnl": realized_pnl,
        "unrealized_pnl": cur_pnl,
        "cashout_value": cashout_value,
        "redeemable": redeemable,
        "status": status,
        "end_date": end_date,
        "raw": raw,
    }


def _build_activity_row(raw: dict) -> dict:
    """Normalize a raw Polymarket activity/trade item."""
    ts = raw.get("timestamp") or raw.get("createdAt") or raw.get("t") or ""
    if isinstance(ts, (int, float)):
        ts = datetime.fromtimestamp(ts, tz=UTC).isoformat().replace("+00:00", "Z")

    side = raw.get("side") or raw.get("type") or ""
    price = float(raw.get("price") or 0)
    size = float(raw.get("size") or 0)
    amount = float(raw.get("usdcSize") or raw.get("amount") or 0)
    if amount == 0 and price > 0:
        amount = price * size

    # Market info
    title = raw.get("title") or raw.get("question") or ""
    slug = raw.get("slug") or ""
    outcome = raw.get("outcome") or raw.get("asset") or ""
    market_slug = raw.get("market_slug") or raw.get("marketSlug") or slug
    trade_id = raw.get("id") or raw.get("tradeId") or ""
    transaction_hash = raw.get("transactionHash") or ""

    return {
        "trade_id": str(trade_id),
        "timestamp": ts,
        "title": title,
        "slug": market_slug,
        "outcome": outcome,
        "side": side.upper() if side else "",
        "price": price,
        "size": size,
        "amount_usdc": amount,
        "transaction_hash": transaction_hash,
        "raw": raw,
    }


def _poll_once(wallet: str, base: str) -> None:
    """Fetch latest data from Polymarket Data API and update cache."""
    # 1. Wallet value
    value_url = f"{base}/value?user={urllib.parse.quote(wallet)}"
    value_raw = _get_json_safe(value_url, default={})
    print(f"[polymarket-poller] value response: {value_raw}", flush=True)

    # 2. All positions
    positions_url = (
        f"{base}/positions?user={urllib.parse.quote(wallet)}"
        "&limit=500&sizeThreshold=0"
    )
    positions_raw = _get_json_safe(positions_url, default=[])
    print(f"[polymarket-poller] positions count: {len(positions_raw) if isinstance(positions_raw, list) else 'not-list'}", flush=True)

    # 3. Trade activity (all time, most recent 500)
    activity_url = (
        f"{base}/activity?user={urllib.parse.quote(wallet)}"
        "&type=TRADE&limit=500"
    )
    activity_raw = _get_json_safe(activity_url, default=[])
    print(f"[polymarket-poller] activity count: {len(activity_raw) if isinstance(activity_raw, list) else 'not-list'}", flush=True)

    # Parse value
    if isinstance(value_raw, list):
        value_row = value_raw[0] if value_raw else {}
    elif isinstance(value_raw, dict):
        value_row = value_raw
    else:
        value_row = {}

    current_value = float((value_row or {}).get("value") or 0.0)

    # Parse positions
    positions = positions_raw if isinstance(positions_raw, list) else []
    parsed_positions = [_build_position_row(p) for p in positions]

    # Aggregate
    open_count = 0
    positions_value = 0.0
    redeemable_value = 0.0
    realized_pnl = 0.0
    unrealized_pnl = 0.0
    for p in parsed_positions:
        if p["status"] == "open":
            open_count += 1
        positions_value += p["current_value"]
        if p["redeemable"]:
            redeemable_value += p["current_value"]
        realized_pnl += p["realized_pnl"]
        unrealized_pnl += p["unrealized_pnl"]

    cash_value = current_value - positions_value
    if abs(cash_value) < 1e-9:
        cash_value = 0.0

    # Parse activity
    activity = activity_raw if isinstance(activity_raw, list) else []
    parsed_activity = [_build_activity_row(a) for a in activity]

    # Build summary
    summary = {
        "wallet": wallet,
        "current_value_usdc": current_value,
        "cash_usdc": cash_value,
        "positions_value_usdc": positions_value,
        "redeemable_usdc": redeemable_value,
        "open_position_count": open_count,
        "positions_realized_pnl_usdc": realized_pnl,
        "positions_unrealized_pnl_usdc": unrealized_pnl,
        "trade_activity_count": len(parsed_activity),
        "polled_at": datetime.now(tz=UTC).isoformat().replace("+00:00", "Z"),
    }

    # Update cache
    with _lock:
        global _wallet_summary, _positions, _activity, _last_poll_at
        _wallet_summary = summary
        _positions = parsed_positions
        _activity = parsed_activity
        _last_poll_at = time.time()

    print(
        f"[polymarket-poller] poll: value=${current_value:.2f} cash=${cash_value:.2f} "
        f"positions=${positions_value:.2f} open={open_count} trades={len(parsed_activity)}",
        flush=True,
    )
    logger.info(
        "polymarket poll: value=$%.2f cash=$%.2f positions=$%.2f open=%d trades=%d",
        current_value,
        cash_value,
        positions_value,
        open_count,
        len(parsed_activity),
    )


# ---------------------------------------------------------------------------
# Background thread
# ---------------------------------------------------------------------------

_stop_event = threading.Event()
_thread: threading.Thread | None = None


def _poller_loop() -> None:
    wallet = (settings.polymarket_overview_wallet or "").strip()
    base = settings.polymarket_data_host.rstrip("/")
    if not wallet:
        print("[polymarket-poller] no POLYMARKET_OVERVIEW_WALLET set, stopping", flush=True)
        logger.warning("polymarket poller: no POLYMARKET_OVERVIEW_WALLET set, stopping")
        return

    print(f"[polymarket-poller] started: wallet={wallet} interval={_POLL_INTERVAL_SECS:.0f}s", flush=True)
    logger.info("polymarket poller started: wallet=%s interval=%.0fs", wallet, _POLL_INTERVAL_SECS)

    while not _stop_event.is_set():
        try:
            _poll_once(wallet, base)
        except Exception as exc:
            print(f"[polymarket-poller] error: {exc}", flush=True)
            logger.exception("polymarket poller: unexpected error")
        _stop_event.wait(timeout=_POLL_INTERVAL_SECS)

    logger.info("polymarket poller stopped")


def start() -> None:
    global _thread
    if _thread is not None and _thread.is_alive():
        return
    _stop_event.clear()
    _thread = threading.Thread(target=_poller_loop, daemon=True, name="polymarket-poller")
    _thread.start()


def stop() -> None:
    _stop_event.set()
    if _thread is not None:
        _thread.join(timeout=5.0)
