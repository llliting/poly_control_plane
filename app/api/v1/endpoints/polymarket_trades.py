from fastapi import APIRouter, Query

from app.services.polymarket_poller import get_activity, get_open_positions, get_positions

router = APIRouter()


@router.get("/polymarket-trades")
def polymarket_trades(
    limit: int = Query(default=200, ge=1, le=1000),
    sort_by: str = Query(default="timestamp"),
    sort_dir: str = Query(default="desc"),
    outcome: str | None = Query(default=None),
    slug: str | None = Query(default=None),
    side: str | None = Query(default=None),
) -> dict:
    rows = get_activity()

    # Apply filters
    if outcome:
        outcome_lower = outcome.lower()
        rows = [r for r in rows if r["outcome"].lower() == outcome_lower]
    if slug:
        slug_lower = slug.lower()
        rows = [r for r in rows if slug_lower in r["slug"].lower()]
    if side:
        side_upper = side.upper()
        rows = [r for r in rows if r["side"] == side_upper]

    # Sort
    sort_key = sort_by
    valid_sort_keys = {"timestamp", "price", "size", "amount_usdc", "slug", "outcome", "side"}
    if sort_key not in valid_sort_keys:
        sort_key = "timestamp"

    reverse = sort_dir.lower() != "asc"
    rows = sorted(rows, key=lambda r: r.get(sort_key) or "", reverse=reverse)

    # Strip raw field for response
    items = [{k: v for k, v in r.items() if k != "raw"} for r in rows[:limit]]

    return {
        "items": items,
        "total": len(rows),
    }


@router.get("/polymarket-positions")
def polymarket_positions(
    status: str = Query(default="all"),
    limit: int = Query(default=200, ge=1, le=1000),
    sort_by: str = Query(default="current_value"),
    sort_dir: str = Query(default="desc"),
) -> dict:
    if status == "open":
        rows = get_open_positions()
    elif status == "all":
        rows = get_positions()
    else:
        all_positions = get_positions()
        rows = [p for p in all_positions if p.get("status") == status]

    # Sort
    valid_sort_keys = {"current_value", "size", "avg_price", "realized_pnl", "unrealized_pnl", "title", "slug"}
    sort_key = sort_by if sort_by in valid_sort_keys else "current_value"
    reverse = sort_dir.lower() != "asc"
    rows = sorted(rows, key=lambda r: r.get(sort_key) or 0, reverse=reverse)

    # Strip raw field
    items = [{k: v for k, v in r.items() if k != "raw"} for r in rows[:limit]]

    print(f"[polymarket-positions] status={status} total={len(rows)} returning={len(items)}", flush=True)

    return {
        "items": items,
        "total": len(rows),
    }
