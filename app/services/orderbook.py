"""Fetch and cache Polymarket CLOB orderbook data."""

from __future__ import annotations

import json
import logging
import time
import urllib.parse
from threading import Lock

from app.core.config import settings
from app.core.http import get_json as _get_json

logger = logging.getLogger(__name__)

_CACHE_TTL_SECS = 3.0
_lock = Lock()
_cache: dict[str, tuple[float, dict]] = {}

CLOB_HOST = "https://clob.polymarket.com"
GAMMA_HOST = "https://gamma-api.polymarket.com"


def _resolve_token_ids(slug: str) -> tuple[str, str] | None:
    """Resolve a market slug to (token_id_0, token_id_1) via gamma API.

    For up/down markets the outcomes are "Up"/"Down" (not "Yes"/"No").
    We use the clobTokenIds field from gamma directly which always has
    [first_outcome_token, second_outcome_token].
    """
    try:
        url = f"{GAMMA_HOST}/markets?slug={urllib.parse.quote(slug)}"
        logger.debug("resolving token IDs for slug=%s url=%s", slug, url)
        items = _get_json(url)
        if not isinstance(items, list) or not items:
            logger.warning("resolve_token_ids: no results for slug=%s", slug)
            return None
        match = next((m for m in items if m.get("slug") == slug), None)
        if not match:
            logger.warning("resolve_token_ids: slug=%s not in %d gamma results", slug, len(items))
            return None
        # clobTokenIds is a JSON-encoded list string like '["id1", "id2"]'
        clob_ids_raw = match.get("clobTokenIds")
        if clob_ids_raw:
            clob_ids = json.loads(clob_ids_raw) if isinstance(clob_ids_raw, str) else clob_ids_raw
            if isinstance(clob_ids, list) and len(clob_ids) >= 2:
                logger.debug("resolved slug=%s -> tokens=%s", slug, clob_ids[:2])
                return (clob_ids[0], clob_ids[1])
        logger.warning("resolve_token_ids: no clobTokenIds for slug=%s", slug)
    except Exception:
        logger.exception("resolve_token_ids failed for slug=%s", slug)
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


def fetch_book(token_id: str) -> dict:
    return _fetch_book(token_id)


def get_orderbook_for_market(slug: str, tokens: list[dict]) -> dict:
    books: list[dict] = []
    for token in tokens[:2]:
        token_id = str(token.get("token_id") or "").strip()
        outcome = str(token.get("outcome") or "").strip() or f"Outcome {len(books) + 1}"
        if not token_id:
            books.append(
                {
                    "token_id": "",
                    "outcome": outcome,
                    "best_bid": None,
                    "best_ask": None,
                    "mid": None,
                    "spread": None,
                    "bids": [],
                    "asks": [],
                }
            )
            continue
        try:
            book = _fetch_book(token_id)
        except Exception:
            book = {"best_bid": None, "best_ask": None, "mid": None, "spread": None, "bids": [], "asks": []}
        books.append({"token_id": token_id, "outcome": outcome, **book})

    result = {
        "slug": slug,
        "books": books,
        "as_of": time.time(),
    }
    if books:
        result["yes"] = books[0]
    if len(books) > 1:
        result["no"] = books[1]
    return result


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
    result = get_orderbook_for_market(
        slug=slug,
        tokens=[
            {"token_id": yes_token, "outcome": "UP"},
            {"token_id": no_token, "outcome": "DOWN"},
        ],
    )

    with _lock:
        _cache[cache_key] = (time.time(), result)

    return result
