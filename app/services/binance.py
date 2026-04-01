"""Fetch and cache live Binance spot prices with 5-minute history."""

from __future__ import annotations

import json
import ssl
import time
import urllib.request
from collections import deque
from threading import Lock

_CACHE_TTL_SECS = 2.0
_HISTORY_WINDOW_SECS = 330  # keep slightly more than 5 min of history
_lock = Lock()

# Per-asset cache: asset -> (fetch_time, price)
_price_cache: dict[str, tuple[float, float]] = {}

# Per-asset price history: asset -> deque of (timestamp, price)
_price_history: dict[str, deque] = {}

BINANCE_API = "https://api.binance.us/api/v3/ticker/price"


_ssl_ctx = ssl.create_default_context()
try:
    import certifi
    _ssl_ctx.load_verify_locations(certifi.where())
except Exception:
    # Fall back to unverified if certifi unavailable and default certs fail
    _ssl_ctx = ssl.create_default_context()
    _ssl_ctx.check_hostname = False
    _ssl_ctx.verify_mode = ssl.CERT_NONE


def _fetch_price(symbol: str, timeout: float = 3.0) -> float:
    url = f"{BINANCE_API}?symbol={symbol}"
    req = urllib.request.Request(url, headers={"User-Agent": "control-plane/1.0"})
    with urllib.request.urlopen(req, timeout=timeout, context=_ssl_ctx) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return float(data["price"])


def _asset_to_symbol(asset: str) -> str:
    return f"{asset.upper()}USDT"


def get_binance_price(asset: str = "BTC") -> dict:
    """Get live Binance price and 5-minute change for the given asset.

    Returns:
        {
            "asset": "BTC",
            "price": 93500.12,
            "price_at_5m_start": 93480.00,   # price ~5 min ago (or earliest available)
            "change_5m": 20.12,               # price - price_at_5m_start
            "as_of": 1711234567.89,
        }
    """
    now = time.time()
    symbol = _asset_to_symbol(asset)
    cache_key = asset.upper()

    # Check cache
    with _lock:
        cached = _price_cache.get(cache_key)
        if cached and now - cached[0] < _CACHE_TTL_SECS:
            price = cached[1]
    if cached and now - cached[0] < _CACHE_TTL_SECS:
        return _build_response(cache_key, price, now)

    # Fetch fresh price
    try:
        price = _fetch_price(symbol)
    except Exception as e:
        # Return last known price if available
        with _lock:
            cached = _price_cache.get(cache_key)
            if cached:
                return _build_response(cache_key, cached[1], now)
        return {
            "asset": cache_key,
            "price": None,
            "price_at_5m_start": None,
            "change_5m": None,
            "as_of": now,
            "error": str(e),
        }

    with _lock:
        _price_cache[cache_key] = (now, price)

        # Append to history
        if cache_key not in _price_history:
            _price_history[cache_key] = deque()
        _price_history[cache_key].append((now, price))

        # Prune old entries
        cutoff = now - _HISTORY_WINDOW_SECS
        hist = _price_history[cache_key]
        while hist and hist[0][0] < cutoff:
            hist.popleft()

    return _build_response(cache_key, price, now)


def _build_response(asset: str, price: float, now: float) -> dict:
    """Build the response dict with 5-min change computed from history."""
    price_at_5m = None
    change_5m = None

    with _lock:
        hist = _price_history.get(asset)
        if hist and len(hist) > 0:
            # Find the price closest to 5 minutes ago
            target_time = now - 300
            # Use earliest entry if we don't have 5 min of data yet
            best = hist[0]
            for ts, px in hist:
                if ts <= target_time:
                    best = (ts, px)
                else:
                    break
            price_at_5m = best[1]
            change_5m = round(price - price_at_5m, 4)

    return {
        "asset": asset,
        "price": price,
        "price_at_5m_start": price_at_5m,
        "change_5m": change_5m,
        "as_of": now,
    }
