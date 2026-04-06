from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services import polymarket_trading

router = APIRouter()


class PlaceOrderRequest(BaseModel):
    token_id: str = Field(description="CLOB token ID for the outcome")
    side: str = Field(description="BUY or SELL")
    price: float = Field(gt=0, le=1, description="Limit price (0-1)")
    size: float = Field(gt=0, description="Number of contracts")
    order_type: str = Field(default="GTC", description="GTC or FAK")
    post_only: bool = Field(default=True, description="Whether the limit order should be post-only")


class PlaceTakerOrderRequest(BaseModel):
    token_id: str = Field(description="CLOB token ID for the outcome")
    side: str = Field(description="BUY or SELL")
    size: float = Field(gt=0, description="Number of contracts")
    order_type: str = Field(default="FAK", description="FAK or FOK")


class ClosePositionRequest(BaseModel):
    token_id: str = Field(description="CLOB token ID of the held outcome")
    size: float = Field(gt=0, description="Number of contracts to close")
    price: float = Field(gt=0, le=1, description="Price to sell at (best bid)")


class CancelOrderRequest(BaseModel):
    order_id: str = Field(description="Order ID to cancel")


@router.get("/trading/status")
def trading_status() -> dict:
    return {"enabled": polymarket_trading.is_enabled()}


@router.get("/trading/open-orders")
def open_orders(token_id: str | None = None) -> dict:
    if not polymarket_trading.is_enabled():
        raise HTTPException(status_code=503, detail="trading not configured")
    orders = polymarket_trading.get_open_orders(token_ids=[token_id] if token_id else None)
    return {"orders": orders}


@router.post("/trading/place-order")
def place_order(req: PlaceOrderRequest) -> dict:
    if not polymarket_trading.is_enabled():
        raise HTTPException(status_code=503, detail="trading not configured")
    if req.side.upper() not in ("BUY", "SELL"):
        raise HTTPException(status_code=400, detail="side must be BUY or SELL")
    result = polymarket_trading.place_limit_order(
        token_id=req.token_id,
        side=req.side.upper(),
        price=req.price,
        size=req.size,
        order_type=req.order_type.upper(),
        post_only=req.post_only,
    )
    if not result.get("success"):
        raise HTTPException(status_code=500, detail=result.get("error", "unknown error"))
    return result


@router.post("/trading/place-taker-order")
def place_taker_order(req: PlaceTakerOrderRequest) -> dict:
    if not polymarket_trading.is_enabled():
        raise HTTPException(status_code=503, detail="trading not configured")
    if req.side.upper() not in ("BUY", "SELL"):
        raise HTTPException(status_code=400, detail="side must be BUY or SELL")
    result = polymarket_trading.place_taker_order(
        token_id=req.token_id,
        side=req.side.upper(),
        size=req.size,
        order_type=req.order_type.upper(),
    )
    if not result.get("success"):
        raise HTTPException(status_code=500, detail=result.get("error", "unknown error"))
    return result


@router.post("/trading/close-position")
def close_position(req: ClosePositionRequest) -> dict:
    if not polymarket_trading.is_enabled():
        raise HTTPException(status_code=503, detail="trading not configured")
    result = polymarket_trading.close_position(
        token_id=req.token_id,
        size=req.size,
        current_price=req.price,
    )
    if not result.get("success"):
        raise HTTPException(status_code=500, detail=result.get("error", "unknown error"))
    return result


@router.post("/trading/cancel-order")
def cancel_order(req: CancelOrderRequest) -> dict:
    if not polymarket_trading.is_enabled():
        raise HTTPException(status_code=503, detail="trading not configured")
    result = polymarket_trading.cancel_order(req.order_id)
    if not result.get("success"):
        raise HTTPException(status_code=500, detail=result.get("error", "unknown error"))
    return result


@router.post("/trading/cancel-all")
def cancel_all() -> dict:
    if not polymarket_trading.is_enabled():
        raise HTTPException(status_code=503, detail="trading not configured")
    result = polymarket_trading.cancel_all_orders()
    if not result.get("success"):
        raise HTTPException(status_code=500, detail=result.get("error", "unknown error"))
    return result
