from fastapi import APIRouter, Query

from app.services.mock_data import get_overview

router = APIRouter()


@router.get("/overview")
def overview(
    service_key: str = Query(default="all"),
    from_date: str = Query(alias="from", default="2026-03-10"),
    to_date: str = Query(alias="to", default="2026-03-12"),
) -> dict:
    return get_overview(service_key=service_key, from_date=from_date, to_date=to_date)

