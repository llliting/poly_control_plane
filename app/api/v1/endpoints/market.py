from fastapi import APIRouter, Query

from app.services.binance import get_binance_price
from app.services.mock_data import get_market_summary, get_market_tape
from app.services.orderbook import get_orderbook

router = APIRouter()


@router.get("/market/summary")
def market_summary(asset: str = Query(default="BTC")) -> dict:
    return get_market_summary(asset=asset)


@router.get("/market/tape")
def market_tape(asset: str = Query(default="BTC"), limit: int = Query(default=100, ge=1, le=500)) -> dict:
    return {"items": get_market_tape(asset=asset, limit=limit)}


@router.get("/market/orderbook")
def market_orderbook(asset: str = Query(default="BTC")) -> dict:
    return get_orderbook(asset=asset)


@router.get("/market/binance-price")
def market_binance_price(asset: str = Query(default="BTC")) -> dict:
    return get_binance_price(asset=asset)

