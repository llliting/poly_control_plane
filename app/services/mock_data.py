from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

SERVICES: list[dict] = [
    {
        "service_key": "btc_5m_main",
        "display_name": "BTC 5m Main",
        "asset": "BTC",
        "timeframe": "5m",
        "strategy_key": "xgb_okx_feature_spec_25f",
        "runner_key": "ec2-a",
        "status": "healthy",
        "signal": "UP",
        "p_up": 0.91,
        "edge": 0.082,
        "traded": True,
        "portfolio_usdc": 24328.12,
        "position_usdc": 9342.38,
        "cash_usdc": 14985.74,
        "git_branch": "no-gate",
        "git_commit": "23903e3",
        "heartbeat_age_sec": 2,
        "model_threshold": 0.85,
        "edge_floor": 0.00,
        "edge_ceiling": 0.40,
        "health": {
            "ready": True,
            "binance_connected": True,
            "okx_connected": True,
            "rtds_connected": True,
            "last_event_age_ms": 420,
            "trade_retries_10m": 1,
            "claimable_usdc": 12.02,
            "process_state": "running",
        },
    },
    {
        "service_key": "eth_5m_main",
        "display_name": "ETH 5m Main",
        "asset": "ETH",
        "timeframe": "5m",
        "strategy_key": "xgb_okx_feature_spec_25f",
        "runner_key": "ec2-b",
        "status": "healthy",
        "signal": "DOWN",
        "p_up": 0.31,
        "edge": 0.071,
        "traded": True,
        "portfolio_usdc": 18743.20,
        "position_usdc": 7211.91,
        "cash_usdc": 11531.29,
        "git_branch": "no-gate",
        "git_commit": "90c32f2",
        "heartbeat_age_sec": 4,
        "model_threshold": 0.85,
        "edge_floor": 0.00,
        "edge_ceiling": 0.40,
        "health": {
            "ready": True,
            "binance_connected": True,
            "okx_connected": True,
            "rtds_connected": True,
            "last_event_age_ms": 530,
            "trade_retries_10m": 4,
            "claimable_usdc": 4.10,
            "process_state": "running",
        },
    },
]

DECISIONS: dict[str, list[dict]] = {
    "btc_5m_main": [
        {
            "decision_id": 102391,
            "ts": "2026-03-12T03:20:55Z",
            "market_slug": "btc-updown-5m-1772484300",
            "side": "UP",
            "p_up": 0.91,
            "threshold": 0.85,
            "edge": 0.081,
            "streak_hits": 3,
            "streak_target": 3,
            "traded": True,
            "market_price": 93422.12,
            "binance_price": 93422.12,
            "binance_price_change_5m": 118.43,
            "danger_f_adx_3m": 0.2142,
            "danger_f_spread_3m": 0.1084,
            "danger_f_er_3m": 0.3321,
            "no_trade_reason": None,
        }
    ],
    "eth_5m_main": [
        {
            "decision_id": 102392,
            "ts": "2026-03-12T03:20:57Z",
            "market_slug": "eth-updown-5m-1772484300",
            "side": "DOWN",
            "p_up": 0.31,
            "threshold": 0.85,
            "edge": 0.074,
            "streak_hits": 3,
            "streak_target": 3,
            "traded": True,
            "market_price": 3288.14,
            "binance_price": 3288.14,
            "binance_price_change_5m": -6.82,
            "danger_f_adx_3m": 0.1825,
            "danger_f_spread_3m": 0.0913,
            "danger_f_er_3m": 0.2841,
            "no_trade_reason": None,
        }
    ],
}

RUNTIME_ROWS: dict[str, list[dict]] = {
    "btc_5m_main": [
        {
            "ts": "2026-03-12T03:20:55Z",
            "binance_price": 93422.12,
            "chainlink_price": 93417.88,
            "pm_mid": 0.432,
            "pm_bid": 0.428,
            "pm_ask": 0.436,
            "cl_bin_spread": -4.24,
            "bucket_seconds_left": 245,
            "ingest_lag_ms": 420,
            "streak_hits": 3,
            "streak_target": 3,
            "binance_price_change_5m": 118.43,
            "danger_f_adx_3m": 0.2142,
            "danger_f_spread_3m": 0.1084,
            "danger_f_er_3m": 0.3321,
        }
    ],
    "eth_5m_main": [
        {
            "ts": "2026-03-12T03:20:57Z",
            "binance_price": 3288.14,
            "chainlink_price": 3287.42,
            "pm_mid": 0.578,
            "pm_bid": 0.571,
            "pm_ask": 0.584,
            "cl_bin_spread": -0.72,
            "bucket_seconds_left": 243,
            "ingest_lag_ms": 530,
            "streak_hits": 3,
            "streak_target": 3,
            "binance_price_change_5m": -6.82,
            "danger_f_adx_3m": 0.1825,
            "danger_f_spread_3m": 0.0913,
            "danger_f_er_3m": 0.2841,
        }
    ],
}

TRADES: list[dict] = [
    {
        "trade_id": "trd_01",
        "service_key": "btc_5m_main",
        "market_slug": "btc-updown-5m-1772484300",
        "open_time": "2026-03-12T03:20:55Z",
        "side": "UP",
        "model_probability": 0.91,
        "entry_price": 0.43,
        "amount_usdc": 22.0,
        "result": "WIN",
        "pnl_usdc": 12.54,
        "pnl_pct": 57.0,
        "status": "settled",
    },
    {
        "trade_id": "trd_02",
        "service_key": "eth_5m_main",
        "market_slug": "eth-updown-5m-1772484300",
        "open_time": "2026-03-12T03:20:57Z",
        "side": "DOWN",
        "model_probability": 0.31,
        "entry_price": 0.61,
        "amount_usdc": 16.0,
        "result": "WIN",
        "pnl_usdc": 6.9,
        "pnl_pct": 43.12,
        "status": "settled",
    },
]

LOGS: list[dict] = [
    {
        "ts": "2026-03-12T03:20:55Z",
        "service_key": "btc_5m_main",
        "level": "info",
        "message": "decision_5m service=btc_5m_main signal=UP traded=true p_up=0.910 edge=0.081",
    },
    {
        "ts": "2026-03-12T03:20:57Z",
        "service_key": "eth_5m_main",
        "level": "info",
        "message": "decision_5m service=eth_5m_main signal=DOWN traded=true p_up=0.310 edge=0.074",
    },
]


def get_services() -> list[dict]:
    return SERVICES


def get_service_or_none(service_key: str) -> dict | None:
    for service in SERVICES:
        if service["service_key"] == service_key:
            return service
    return None


def get_overview(service_key: str, from_date: str, to_date: str) -> dict:
    selected_services = SERVICES if service_key == "all" else [s for s in SERVICES if s["service_key"] == service_key]
    total_pnl = sum(t["pnl_usdc"] for t in TRADES if service_key == "all" or t["service_key"] == service_key)
    wins = sum(1 for t in TRADES if (service_key == "all" or t["service_key"] == service_key) and t["result"] == "WIN")
    losses = sum(1 for t in TRADES if (service_key == "all" or t["service_key"] == service_key) and t["result"] == "LOSS")
    trade_count = wins + losses
    avg_pnl = total_pnl / trade_count if trade_count else 0.0

    return {
        "stats": {
            "runners_online": 2,
            "runners_total": 2,
            "services_healthy": sum(1 for s in SERVICES if s["status"] == "healthy"),
            "services_total": len(SERVICES),
            "pnl_today_usdc": total_pnl,
            "open_alerts": 1,
        },
        "services": [
            {
                "service_key": s["service_key"],
                "runner_key": s["runner_key"],
                "status": s["status"],
                "signal": s["signal"],
                "p_up": s["p_up"],
                "edge": s["edge"],
                "traded": s["traded"],
                "portfolio_usdc": s["portfolio_usdc"],
                "position_usdc": s["position_usdc"],
                "cash_usdc": s["cash_usdc"],
                "git_commit": s["git_commit"],
                "heartbeat_age_sec": s["heartbeat_age_sec"],
            }
            for s in selected_services
        ],
        "range_summary": {
            "from": from_date,
            "to": to_date,
            "service_key": service_key,
            "realized_pnl_usdc": round(total_pnl, 4),
            "wins": wins,
            "losses": losses,
            "trade_count": trade_count,
            "avg_pnl_usdc": round(avg_pnl, 6),
        },
        "charts": {
            "portfolio_curve": [
                {"ts": "2026-03-10T00:00:00Z", "value_usdc": 42000.00},
                {"ts": "2026-03-12T00:00:00Z", "value_usdc": 42000.00 + total_pnl},
            ],
            "cumulative_pnl_curve": [
                {"ts": "2026-03-10T00:00:00Z", "value_usdc": 0.0},
                {"ts": "2026-03-12T00:00:00Z", "value_usdc": total_pnl},
            ],
        },
        "incidents": [
            {
                "incident_id": "inc_01",
                "severity": "warn",
                "message": "eth_5m_main trade retry spike in last 10m",
                "status": "open",
                "opened_at": "2026-03-12T03:21:15Z",
            }
        ],
    }


def get_market_summary(asset: str) -> dict:
    if asset.upper() == "ETH":
        binance_price = 3288.14
        chainlink_price = 3287.42
        market_slug = "eth-updown-5m-1772484300"
    else:
        asset = "BTC"
        binance_price = 93422.12
        chainlink_price = 93417.88
        market_slug = "btc-updown-5m-1772484300"

    return {
        "asset": asset,
        "binance_price": binance_price,
        "chainlink_price": chainlink_price,
        "spread": round(binance_price - chainlink_price, 2),
        "market_slug": market_slug,
        "as_of": "2026-03-12T03:20:55Z",
    }


def get_market_tape(asset: str, limit: int) -> list[dict]:
    summary = get_market_summary(asset)
    now = datetime.now(tz=UTC)
    rows: list[dict] = []
    for idx in range(limit):
        ts = now.replace(microsecond=0).isoformat().replace("+00:00", "Z")
        rows.append(
            {
                "ts": ts,
                "symbol": f"{summary['asset']}USD",
                "binance_price": summary["binance_price"] - idx * 0.12,
                "chainlink_price": summary["chainlink_price"] - idx * 0.11,
                "spread": summary["spread"] - idx * 0.01,
                "stale": idx > 20,
            }
        )
    return rows


def request_action(service_key: str, action: str) -> dict:
    return {
        "action_id": str(uuid4()),
        "service_key": service_key,
        "action": action,
        "status": "queued",
        "requested_at": datetime.now(tz=UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
    }
