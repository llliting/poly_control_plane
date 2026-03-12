from fastapi import APIRouter, Query

from app.services.mock_data import TRADES

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
    rows = TRADES if service_key == "all" else [trade for trade in TRADES if trade["service_key"] == service_key]
    reverse = sort_dir.lower() != "asc"
    rows = sorted(rows, key=lambda row: row["open_time"], reverse=reverse)
    return {
        "items": rows[:limit],
        "next_cursor": None,
    }

