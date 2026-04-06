from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.services import polymarket_trading
from app.services.liquidity_rewards import get_market_by_slug, list_rewards_markets
from app.services.orderbook import get_orderbook_for_market

router = APIRouter()


@router.get("/liquidity-rewards/markets")
def liquidity_rewards_markets(
    q: str | None = Query(default=None),
    category: str | None = Query(default=None),
    order_by: str | None = Query(default=None),
    position: str | None = Query(default=None),
) -> dict:
    return list_rewards_markets(q=q, category=category, order_by=order_by, position=position)


@router.get("/liquidity-rewards/market")
def liquidity_rewards_market(slug: str = Query(..., min_length=1)) -> dict:
    market = get_market_by_slug(slug)
    if not market:
        raise HTTPException(status_code=404, detail="market not found")
    return market


@router.get("/liquidity-rewards/orderbook")
def liquidity_rewards_orderbook(slug: str = Query(..., min_length=1)) -> dict:
    market = get_market_by_slug(slug)
    if not market:
        raise HTTPException(status_code=404, detail="market not found")
    return get_orderbook_for_market(slug=market["market_slug"], tokens=market.get("tokens") or [])


@router.get("/liquidity-rewards/open-orders")
def liquidity_rewards_open_orders(slug: str = Query(..., min_length=1)) -> dict:
    if not polymarket_trading.is_enabled():
        raise HTTPException(status_code=503, detail="trading not configured")
    market = get_market_by_slug(slug)
    if not market:
        raise HTTPException(status_code=404, detail="market not found")
    token_ids = [str(token.get("token_id") or "") for token in (market.get("tokens") or []) if token.get("token_id")]
    orders = polymarket_trading.get_open_orders(token_ids=token_ids)
    return {"orders": orders}
