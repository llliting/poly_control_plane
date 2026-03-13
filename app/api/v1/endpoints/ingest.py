from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field

from app.core.config import settings
from app.services.log_stream import append_log
from app.services.repository import upsert_decision, upsert_trade

router = APIRouter()


def verify_ingest_key(x_ingest_key: str | None = Header(default=None)) -> None:
    # If INGEST_API_KEY is set, every ingest request must provide it.
    if settings.ingest_api_key and x_ingest_key != settings.ingest_api_key:
        raise HTTPException(status_code=401, detail="invalid ingest key")


class RuntimeIngest(BaseModel):
    service_key: str
    captured_at: str | None = None
    status: str = "healthy"
    signal: str | None = None
    p_up: float | None = None
    edge: float | None = None
    traded: bool | None = None
    portfolio_usdc: float | None = None
    position_usdc: float | None = None
    cash_usdc: float | None = None
    binance_price: float | None = None
    chainlink_price: float | None = None
    pm_mid: float | None = None
    pm_bid: float | None = None
    pm_ask: float | None = None
    cl_bin_spread: float | None = None
    bucket_seconds_left: int | None = None
    ingest_lag_ms: int | None = None
    streak_hits: int | None = None
    streak_target: int | None = None


class DecisionIngest(BaseModel):
    service_key: str
    occurred_at: str
    market_slug: str
    side: str
    p_up: float
    threshold: float
    edge: float
    streak_hits: int
    streak_target: int
    traded: bool
    market_price: float | None = None
    no_trade_reason: str | None = None


class TradeIngest(BaseModel):
    service_key: str
    market_slug: str
    open_time: str
    side: str
    model_probability: float
    entry_price: float
    market_price: float | None = None
    amount_usdc: float
    result: str
    pnl_usdc: float
    status: str = "settled"


class LogIngest(BaseModel):
    service_key: str
    ts: str | None = None
    level: str = "info"
    message: str


class BatchIngest(BaseModel):
    runtime: list[RuntimeIngest] = Field(default_factory=list)  # accepted for backward compatibility
    decisions: list[DecisionIngest] = Field(default_factory=list)
    trades: list[TradeIngest] = Field(default_factory=list)
    logs: list[LogIngest] = Field(default_factory=list)


@router.post("/ingest/runtime", dependencies=[Depends(verify_ingest_key)])
def ingest_runtime(payload: RuntimeIngest) -> dict:
    # Hybrid mode: runtime snapshots are not persisted to DB.
    _ = payload
    return {"ok": True, "status": "ignored"}


@router.post("/ingest/decision", dependencies=[Depends(verify_ingest_key)])
def ingest_decision(payload: DecisionIngest) -> dict:
    result = upsert_decision(payload.model_dump())
    if result is None:
        raise HTTPException(status_code=503, detail="database not configured")
    return {"ok": True, **result}


@router.post("/ingest/trade", dependencies=[Depends(verify_ingest_key)])
def ingest_trade(payload: TradeIngest) -> dict:
    result = upsert_trade(payload.model_dump())
    if result is None:
        raise HTTPException(status_code=503, detail="database not configured")
    return {"ok": True, **result}


@router.post("/ingest/log", dependencies=[Depends(verify_ingest_key)])
def ingest_log(payload: LogIngest) -> dict:
    data = payload.model_dump()
    if not data.get("ts"):
        data["ts"] = datetime.now(tz=UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    append_log(data)
    return {"ok": True, "status": "accepted"}


@router.post("/ingest/batch", dependencies=[Depends(verify_ingest_key)])
def ingest_batch(payload: BatchIngest) -> dict:
    decision_results: list[dict] = []
    trade_results: list[dict] = []
    log_results: list[dict] = []

    # Runtime items are intentionally ignored in hybrid mode.
    _ = payload.runtime

    for item in payload.decisions:
        result = upsert_decision(item.model_dump())
        if result is not None:
            decision_results.append(result)

    for item in payload.trades:
        result = upsert_trade(item.model_dump())
        if result is not None:
            trade_results.append(result)

    for item in payload.logs:
        data = item.model_dump()
        if not data.get("ts"):
            data["ts"] = datetime.now(tz=UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        append_log(data)
        log_results.append({"status": "accepted"})

    return {
        "ok": True,
        "counts": {
            "runtime": 0,
            "decisions": len(decision_results),
            "trades": len(trade_results),
            "logs": len(log_results),
        },
        "runtime": [],
        "decisions": decision_results,
        "trades": trade_results,
        "logs": log_results,
    }
