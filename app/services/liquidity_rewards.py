from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request
from threading import Lock


CLOB_HOST = "https://clob.polymarket.com"
_CACHE_TTL_SECS = 20.0
_lock = Lock()
_cache: dict[tuple[str, str], tuple[float, dict]] = {}

_CATEGORY_PRIORITY = [
    "politics",
    "sports",
    "crypto",
    "pop-culture",
    "middle-east",
    "business",
    "science",
]
_CATEGORY_LABELS = {
    "politics": "Politics",
    "sports": "Sports",
    "crypto": "Crypto",
    "pop-culture": "Pop Culture",
    "middle-east": "Middle East",
    "business": "Business",
    "science": "Science",
}


def _get_json(url: str, timeout: float = 8.0) -> dict | list:
    req = urllib.request.Request(url, headers={"User-Agent": "control-plane/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _cached(key: tuple[str, str], loader) -> dict:
    now = time.time()
    with _lock:
        cached = _cache.get(key)
        if cached and now - cached[0] < _CACHE_TTL_SECS:
            return cached[1]
    value = loader()
    with _lock:
        _cache[key] = (time.time(), value)
    return value


def _build_query(params: dict[str, str | None]) -> str:
    filtered: list[tuple[str, str]] = []
    for key, value in params.items():
        if value is None or value == "":
            continue
        filtered.append((key, str(value)))
    return urllib.parse.urlencode(filtered, doseq=True)


def _detect_category(item: dict) -> str:
    candidates: list[str] = []
    for key in ("tag_slug", "category_slug", "category", "event_category"):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            candidates.append(value.strip().lower())
    for key in ("tag_slugs", "tags", "categories"):
        value = item.get(key)
        if isinstance(value, list):
            for entry in value:
                if isinstance(entry, str):
                    candidates.append(entry.strip().lower())
                elif isinstance(entry, dict):
                    slug = entry.get("slug")
                    label = entry.get("label")
                    if isinstance(slug, str):
                        candidates.append(slug.strip().lower())
                    if isinstance(label, str):
                        candidates.append(label.strip().lower())
    for slug in _CATEGORY_PRIORITY:
        if slug in candidates:
            return slug
    for candidate in candidates:
        normalized = candidate.replace(" ", "-")
        if normalized:
            return normalized
    return "other"


def _normalize_tokens(item: dict) -> list[dict]:
    tokens = item.get("tokens")
    normalized: list[dict] = []
    if not isinstance(tokens, list):
        return normalized
    for token in tokens:
        if not isinstance(token, dict):
            continue
        token_id = str(token.get("token_id") or token.get("tokenId") or "").strip()
        outcome = str(token.get("outcome") or "").strip() or f"Outcome {len(normalized) + 1}"
        price = token.get("price")
        normalized.append(
            {
                "token_id": token_id,
                "outcome": outcome,
                "price": float(price) if price is not None else None,
            }
        )
    return normalized


def _daily_reward(item: dict) -> float:
    if item.get("total_daily_rate") is not None:
        return float(item.get("total_daily_rate") or 0)
    configs = item.get("rewards_config") or []
    total = 0.0
    for config in configs:
        if isinstance(config, dict):
            total += float(config.get("rate_per_day") or 0)
    return total


def _normalize_market(item: dict) -> dict:
    category_slug = _detect_category(item)
    market_slug = str(item.get("market_slug") or item.get("slug") or "").strip()
    question = str(item.get("question") or item.get("title") or market_slug).strip()
    tokens = _normalize_tokens(item)
    return {
        "condition_id": str(item.get("condition_id") or "").strip(),
        "market_id": str(item.get("market_id") or item.get("id") or "").strip(),
        "market_slug": market_slug,
        "question": question,
        "event_slug": item.get("event_slug"),
        "category": _CATEGORY_LABELS.get(category_slug, category_slug.replace("-", " ").title()),
        "category_slug": category_slug,
        "rewards_min_size": float(item.get("rewards_min_size") or 0),
        "rewards_max_spread": float(item.get("rewards_max_spread") or 0),
        "reward_per_day": _daily_reward(item),
        "spread": float(item.get("spread") or 0) if item.get("spread") is not None else None,
        "volume_24hr": float(item.get("volume_24hr") or 0) if item.get("volume_24hr") is not None else None,
        "price": float(item.get("price") or 0) if item.get("price") is not None else None,
        "one_day_price_change": float(item.get("one_day_price_change") or 0)
        if item.get("one_day_price_change") is not None
        else None,
        "end_date": item.get("end_date"),
        "image": item.get("image"),
        "tokens": tokens,
        "raw": item,
    }


def _fetch_rewards_markets(
    q: str | None = None,
    category: str | None = None,
    order_by: str | None = None,
    position: str | None = None,
) -> dict:
    items: list[dict] = []
    next_cursor: str | None = None
    while True:
        params = {
            "page_size": "500",
            "q": (q or "").strip() or None,
            "tag_slug": (category or "").strip() or None,
            "order_by": (order_by or "").strip() or None,
            "position": (position or "").strip() or None,
            "next_cursor": next_cursor,
        }
        url = f"{CLOB_HOST}/rewards/markets/multi"
        query = _build_query(params)
        if query:
            url = f"{url}?{query}"
        payload = _get_json(url)
        if not isinstance(payload, dict):
            break
        rows = payload.get("data") or []
        if not isinstance(rows, list):
            break
        items.extend(_normalize_market(row) for row in rows if isinstance(row, dict))
        next_cursor = str(payload.get("next_cursor") or "LTE=")
        if next_cursor == "LTE=" or not rows:
            break
    categories = sorted(
        {
            item["category_slug"]: item["category"]
            for item in items
            if item.get("category_slug") and item.get("category")
        }.items(),
        key=lambda pair: pair[1].lower(),
    )
    return {
        "items": items,
        "total": len(items),
        "categories": [{"slug": slug, "label": label} for slug, label in categories],
        "as_of": time.time(),
    }


def list_rewards_markets(
    q: str | None = None,
    category: str | None = None,
    order_by: str | None = None,
    position: str | None = None,
) -> dict:
    cache_key = json.dumps(
        {
            "q": (q or "").strip().lower(),
            "category": (category or "").strip().lower(),
            "order_by": (order_by or "").strip().lower(),
            "position": (position or "").strip().upper(),
        },
        sort_keys=True,
    )
    return _cached(("rewards_markets", cache_key), lambda: _fetch_rewards_markets(q, category, order_by, position))


def get_market_by_slug(slug: str) -> dict | None:
    target = (slug or "").strip().lower()
    if not target:
        return None
    data = list_rewards_markets()
    return next((item for item in data["items"] if (item.get("market_slug") or "").lower() == target), None)
