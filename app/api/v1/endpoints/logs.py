from fastapi import APIRouter, Query

from app.services.mock_data import LOGS

router = APIRouter()


@router.get("/logs")
def logs(service_key: str = Query(default="all"), limit: int = Query(default=200, ge=1, le=1000)) -> dict:
    rows = LOGS if service_key == "all" else [row for row in LOGS if row["service_key"] == service_key]
    rows = sorted(rows, key=lambda row: row["ts"], reverse=True)
    return {"items": rows[:limit]}

