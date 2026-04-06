from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request
from threading import Lock


CLOB_HOST = "https://clob.polymarket.com"
GAMMA_HOST = "https://gamma-api.polymarket.com"
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


def _safe_float(value, default: float | None = 0.0) -> float | None:
    if value is None or value == "":
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


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
                "price": _safe_float(price, None),
            }
        )
    return normalized


def _daily_reward(item: dict) -> float:
    if item.get("total_daily_rate") is not None:
        return _safe_float(item.get("total_daily_rate"), 0.0) or 0.0
    configs = item.get("rewards_config") or []
    total = 0.0
    for config in configs:
        if isinstance(config, dict):
            total += _safe_float(config.get("rate_per_day"), 0.0) or 0.0
    return total


def _lookup_gamma_market(condition_id: str) -> dict | None:
    if not condition_id:
        return None
    url = f"{GAMMA_HOST}/markets?condition_ids={urllib.parse.quote(condition_id)}"
    payload = _get_json(url)
    if not isinstance(payload, list):
        return None
    return next((item for item in payload if isinstance(item, dict) and item.get("conditionId") == condition_id), None)


def _lookup_gamma_market_by_slug(slug: str) -> dict | None:
    if not slug:
        return None
    url = f"{GAMMA_HOST}/markets?slug={urllib.parse.quote(slug)}"
    payload = _get_json(url)
    if not isinstance(payload, list):
        return None
    target = slug.strip().lower()
    return next((item for item in payload if isinstance(item, dict) and str(item.get("slug") or "").lower() == target), None)


def _fetch_market_rewards(condition_id: str) -> dict | None:
    if not condition_id:
        return None
    url = f"{CLOB_HOST}/rewards/markets/{urllib.parse.quote(condition_id)}"
    payload = _get_json(url)
    if not isinstance(payload, dict):
        return None
    rows = payload.get("data") or []
    if not isinstance(rows, list) or not rows:
        return None
    row = rows[0]
    if not isinstance(row, dict):
        return None
    return row


def _merge_with_gamma(item: dict, gamma_market: dict | None) -> dict:
    if not gamma_market:
        return item
    merged = dict(item)
    if not merged.get("question"):
        merged["question"] = gamma_market.get("question") or gamma_market.get("title")
    if not merged.get("market_slug"):
        merged["market_slug"] = gamma_market.get("slug")
    if not merged.get("event_slug"):
        merged["event_slug"] = gamma_market.get("eventSlug") or gamma_market.get("event_slug")
    if not merged.get("image"):
        merged["image"] = gamma_market.get("image")
    if not merged.get("tokens"):
        outcomes = gamma_market.get("outcomes")
        prices = gamma_market.get("outcomePrices")
        clob_ids = gamma_market.get("clobTokenIds")
        try:
            if isinstance(outcomes, str):
                outcomes = json.loads(outcomes)
            if isinstance(prices, str):
                prices = json.loads(prices)
            if isinstance(clob_ids, str):
                clob_ids = json.loads(clob_ids)
        except Exception:
            outcomes, prices, clob_ids = None, None, None
        if isinstance(outcomes, list) and isinstance(clob_ids, list):
            tokens = []
            for idx, token_id in enumerate(clob_ids):
                outcome = outcomes[idx] if idx < len(outcomes) else f"Outcome {idx + 1}"
                price = prices[idx] if isinstance(prices, list) and idx < len(prices) else None
                tokens.append({"token_id": str(token_id), "outcome": str(outcome), "price": _safe_float(price, None)})
            merged["tokens"] = tokens
    return merged


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
        "rewards_min_size": _safe_float(item.get("rewards_min_size"), 0.0) or 0.0,
        "rewards_max_spread": _safe_float(item.get("rewards_max_spread"), 0.0) or 0.0,
        "reward_per_day": _daily_reward(item),
        "spread": _safe_float(item.get("spread"), None),
        "volume_24hr": _safe_float(item.get("volume_24hr"), None),
        "price": _safe_float(item.get("price"), None),
        "one_day_price_change": _safe_float(item.get("one_day_price_change"), None),
        "end_date": item.get("end_date"),
        "image": item.get("image"),
        "tokens": tokens,
        "raw": item,
    }


def _filter_and_sort_items(
    items: list[dict],
    q: str | None = None,
    category: str | None = None,
    order_by: str | None = None,
    position: str | None = None,
) -> list[dict]:
    filtered = list(items)
    query = (q or "").strip().lower()
    if query:
        filtered = [
            item
            for item in filtered
            if query in str(item.get("market_slug") or "").lower()
            or query in str(item.get("question") or "").lower()
            or query in str(item.get("event_slug") or "").lower()
        ]
    category_slug = (category or "").strip().lower()
    if category_slug:
        filtered = [item for item in filtered if str(item.get("category_slug") or "").lower() == category_slug]

    sort_key_map = {
        "market_id": "market_id",
        "created_at": "created_at",
        "volume_24hr": "volume_24hr",
        "spread": "spread",
        "competitiveness": "market_competitiveness",
        "max_spread": "rewards_max_spread",
        "min_size": "rewards_min_size",
        "question": "question",
        "one_day_price_change": "one_day_price_change",
        "rate_per_day": "reward_per_day",
        "price": "price",
        "end_date": "end_date",
        "start_date": "start_date",
        "reward_end_date": "reward_end_date",
    }
    internal_key = sort_key_map.get((order_by or "").strip().lower())
    if internal_key:
        reverse = (position or "DESC").strip().upper() != "ASC"
        filtered.sort(
            key=lambda item: (item.get(internal_key) is None, item.get(internal_key) if item.get(internal_key) is not None else ""),
            reverse=reverse,
        )
    return filtered


def _build_response(items: list[dict], source: str, error: str | None = None) -> dict:
    categories = sorted(
        {
            item["category_slug"]: item["category"]
            for item in items
            if item.get("category_slug") and item.get("category")
        }.items(),
        key=lambda pair: pair[1].lower(),
    )
    payload = {
        "items": items,
        "total": len(items),
        "categories": [{"slug": slug, "label": label} for slug, label in categories],
        "as_of": time.time(),
        "source": source,
    }
    if error:
        payload["error"] = error
    return payload


def _fetch_rewards_markets_via_current(
    q: str | None = None,
    category: str | None = None,
    order_by: str | None = None,
    position: str | None = None,
) -> dict:
    items: list[dict] = []
    next_cursor: str | None = None
    while True:
        params = {"next_cursor": next_cursor}
        url = f"{CLOB_HOST}/rewards/markets/current"
        query = _build_query(params)
        if query:
            url = f"{url}?{query}"
        payload = _get_json(url)
        if not isinstance(payload, dict):
            break
        rows = payload.get("data") or []
        if not isinstance(rows, list) or not rows:
            break
        for row in rows:
            if not isinstance(row, dict):
                continue
            condition_id = str(row.get("condition_id") or "").strip()
            try:
                detail = _fetch_market_rewards(condition_id) or row
            except Exception:
                detail = row
            try:
                gamma = _lookup_gamma_market(condition_id)
            except Exception:
                gamma = None
            item = _merge_with_gamma(detail, gamma)
            items.append(_normalize_market(item))
        next_cursor = str(payload.get("next_cursor") or "LTE=")
        if next_cursor == "LTE=":
            break
    return _build_response(_filter_and_sort_items(items, q, category, order_by, position), source="current")


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
    return _build_response(items, source="multi")


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
    def _load() -> dict:
        errors: list[str] = []
        try:
            return _fetch_rewards_markets_via_current(q, category, order_by, position)
        except Exception as exc:
            errors.append(f"current:{exc}")
        try:
            return _fetch_rewards_markets(q, category, order_by, position)
        except Exception as exc:
            errors.append(f"multi:{exc}")
        return _build_response([], source="unavailable", error="; ".join(errors))

    return _cached(("rewards_markets", cache_key), _load)


def get_market_by_slug(slug: str) -> dict | None:
    target = (slug or "").strip().lower()
    if not target:
        return None
    data = list_rewards_markets()
    cached = next((item for item in data["items"] if (item.get("market_slug") or "").lower() == target), None)
    if cached:
        return cached
    try:
        gamma = _lookup_gamma_market_by_slug(slug)
        if not gamma:
            return None
        condition_id = str(gamma.get("conditionId") or "").strip()
        detail = _fetch_market_rewards(condition_id) or {}
        item = _merge_with_gamma(detail, gamma)
        if not item.get("market_slug"):
            item["market_slug"] = slug
        if not item.get("condition_id"):
            item["condition_id"] = condition_id
        return _normalize_market(item)
    except Exception:
        return None
