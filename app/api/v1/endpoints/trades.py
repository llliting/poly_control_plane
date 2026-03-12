from fastapi import APIRouter, Query

from app.services.mock_data import TRADES
from app.services.repository import list_trades_from_db

router = APIRouter()


@router.get("/trades")
def trades(
    service_key: str = Query(default="all"),
    limit: int = Query(default=200, ge=1, le=1000),
    sort_by: str = Query(default="open_time"),
    sort_dir: str = Query(default="desc"),
    cursor: str | None = Query(default=None),
) -> dict:
    del sort_by, cursor
    rows = None
    try:
        rows = list_trades_from_db(service_key=service_key, limit=limit, sort_dir=sort_dir)
    except Exception:
        rows = None

    if rows is None:
        raw_rows = TRADES if service_key == "all" else [trade for trade in TRADES if trade["service_key"] == service_key]
        reverse = sort_dir.lower() != "asc"
        rows = sorted(raw_rows, key=lambda row: row["open_time"], reverse=reverse)[:limit]

    return {
        "items": rows,
        "next_cursor": None,
    }
