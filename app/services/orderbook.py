"""Fetch and cache Polymarket CLOB orderbook data."""

from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request
from threading import Lock

from app.core.config import settings

_CACHE_TTL_SECS = 3.0
_lock = Lock()
_cache: dict[str, tuple[float, dict]] = {}

CLOB_HOST = "https://clob.polymarket.com"
GAMMA_HOST = "https://gamma-api.polymarket.com"


def _get_json(url: str, timeout: float = 4.0) -> dict | list:
    req = urllib.request.Request(url, headers={"User-Agent": "control-plane/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _resolve_token_ids(slug: str) -> tuple[str, str] | None:
    """Resolve a market slug to (yes_token_id, no_token_id) via gamma + CLOB APIs."""
    try:
        url = f"{GAMMA_HOST}/markets?slug={urllib.parse.quote(slug)}"
        items = _get_json(url)
        if not isinstance(items, list) or not items:
            return None
        match = next((m for m in items if m.get("slug") == slug), None)
        if not match:
            return None
        condition_id = match.get("conditionId")
        if not condition_id:
            return None

        market_url = f"{CLOB_HOST}/markets/{condition_id}"
        market = _get_json(market_url)
        tokens = market.get("tokens", [])
        yes_token = None
        no_token = None
        for t in tokens:
            outcome = (t.get("outcome") or "").upper()
            if outcome == "YES":
                yes_token = t.get("token_id")
            elif outcome == "NO":
                no_token = t.get("token_id")
        if yes_token and no_token:
            return (yes_token, no_token)
    except Exception:
        pass
    return None


def _fetch_book(token_id: str) -> dict:
    """Fetch orderbook for a single token from the CLOB API."""
    url = f"{CLOB_HOST}/book?token_id={urllib.parse.quote(token_id)}"
    data = _get_json(url)
    bids = sorted(
        [
            {"price": float(b.get("price", 0)), "size": float(b.get("size", 0))}
            for b in (data.get("bids") or [])
        ],
        key=lambda x: -x["price"],
    )
    asks = sorted(
        [
            {"price": float(a.get("price", 0)), "size": float(a.get("size", 0))}
            for a in (data.get("asks") or [])
        ],
        key=lambda x: x["price"],
    )
    best_bid = bids[0]["price"] if bids else None
    best_ask = asks[0]["price"] if asks else None
    mid = round((best_bid + best_ask) / 2, 4) if best_bid is not None and best_ask is not None else None
    spread = round(best_ask - best_bid, 4) if best_bid is not None and best_ask is not None else None
    return {
        "best_bid": best_bid,
        "best_ask": best_ask,
        "mid": mid,
        "spread": spread,
        "bids": bids[:10],
        "asks": asks[:10],
    }


def _compute_slug(asset: str) -> str:
    """Compute the current 5-min market slug for the given asset."""
    prefix = f"{asset.lower()}-updown-5m"
    now_s = int(time.time())
    bucket_start_s = now_s - (now_s % 300)
    return f"{prefix}-{bucket_start_s}"


def get_orderbook(asset: str = "BTC") -> dict:
    """Get the orderbook for the current active market.

    Returns YES and NO side books with top-of-book quotes.
    Cached for a few seconds to avoid hammering the CLOB API.
    """
    slug = _compute_slug(asset)
    cache_key = slug

    with _lock:
        cached = _cache.get(cache_key)
        if cached and time.time() - cached[0] < _CACHE_TTL_SECS:
            return cached[1]

    # Resolve token IDs (also try previous bucket as fallback near boundaries)
    tokens = _resolve_token_ids(slug)
    fallback_slug = None
    if not tokens:
        now_s = int(time.time())
        bucket_start_s = now_s - (now_s % 300)
        fallback_slug = f"{asset.lower()}-updown-5m-{bucket_start_s - 300}"
        tokens = _resolve_token_ids(fallback_slug)
    if not tokens:
        return {
            "slug": slug,
            "fallback_slug": fallback_slug,
            "error": "market_not_found",
            "yes": None,
            "no": None,
        }

    yes_token, no_token = tokens
    try:
        yes_book = _fetch_book(yes_token)
    except Exception:
        yes_book = {"best_bid": None, "best_ask": None, "mid": None, "spread": None, "bids": [], "asks": []}
    try:
        no_book = _fetch_book(no_token)
    except Exception:
        no_book = {"best_bid": None, "best_ask": None, "mid": None, "spread": None, "bids": [], "asks": []}

    result = {
        "slug": slug,
        "yes": yes_book,
        "no": no_book,
        "as_of": time.time(),
    }

    with _lock:
        _cache[cache_key] = (time.time(), result)

    return result
