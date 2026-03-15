from fastapi import APIRouter, Query

from app.core.config import settings
from app.services.polymarket_data import fetch_wallet_summary
from app.services.polymarket_poller import get_open_positions, get_wallet_summary
from app.services.repository import get_overview_from_db, list_services_from_db
from app.services.runtime_state import overlay_service_row, runtime_overview_money

router = APIRouter()


def _empty_overview(service_key: str, from_date: str, to_date: str) -> dict:
    services = list_services_from_db() or []
    selected_services = (
        services if service_key == "all" else [s for s in services if s["service_key"] == service_key]
    )
    selected_services = [overlay_service_row(row) for row in selected_services]
    runners_total = len({s["runner_key"] for s in services})
    runners_online = len({s["runner_key"] for s in services if s["status"] != "stopped"})
    services_healthy = sum(1 for s in services if s["status"] == "healthy")
    open_alerts = sum(1 for s in services if s["status"] not in {"healthy", "stopped"})
    return {
        "stats": {
            "runners_online": runners_online,
            "runners_total": runners_total,
            "services_healthy": services_healthy,
            "services_total": len(services),
            "pnl_today_usdc": 0.0,
            "open_alerts": open_alerts,
            "portfolio_value_usdc": 0.0,
            "positions_value_usdc": 0.0,
            "cash_usdc": 0.0,
            "redeemable_usdc": 0.0,
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
            "realized_pnl_usdc": 0.0,
            "wins": 0,
            "losses": 0,
            "trade_count": 0,
            "avg_pnl_usdc": 0.0,
        },
        "charts": {
            "portfolio_curve": [],
            "cumulative_pnl_curve": [{"ts": f"{from_date}T00:00:00Z", "value_usdc": 0.0}],
        },
        "incidents": [],
        "open_positions": [],
    }


@router.get("/overview")
def overview(
    service_key: str = Query(default="all"),
    from_date: str = Query(alias="from", default="2026-03-10"),
    to_date: str = Query(alias="to", default="2026-03-12"),
) -> dict:
    data = _empty_overview(service_key=service_key, from_date=from_date, to_date=to_date)
    try:
        db_data = get_overview_from_db(service_key=service_key, from_date=from_date, to_date=to_date)
        if db_data is not None:
            data = db_data
            data.setdefault("open_positions", [])
    except Exception:
        pass

    data["services"] = [overlay_service_row(row) for row in data.get("services", [])]
    runtime_money = runtime_overview_money(
        [str(row.get("service_key") or "").strip() for row in data.get("services", [])]
    )

    # Prefer poller data (always fresh), fall back to one-shot fetch
    poller_summary = get_wallet_summary()
    wallet_summary = poller_summary
    if wallet_summary is None:
        wallet_summary = fetch_wallet_summary(
            wallet=settings.polymarket_overview_wallet or "",
            from_date=from_date,
            to_date=to_date,
        )

    if wallet_summary is not None:
        current_value = wallet_summary["current_value_usdc"]
        total_pnl = data["range_summary"]["realized_pnl_usdc"]
        base_value = current_value - total_pnl
        pnl_curve = data["charts"]["cumulative_pnl_curve"]
        portfolio_curve = []
        for point in pnl_curve:
            portfolio_curve.append(
                {
                    "ts": point["ts"],
                    "value_usdc": round(base_value + float(point["value_usdc"] or 0.0), 6),
                }
            )
        if not portfolio_curve:
            portfolio_curve = [{"ts": f"{to_date}T00:00:00Z", "value_usdc": round(current_value, 6)}]
        data["charts"]["portfolio_curve"] = portfolio_curve
        data["stats"]["portfolio_value_usdc"] = round(current_value, 4)
        data["stats"]["positions_value_usdc"] = round(wallet_summary["positions_value_usdc"], 4)
        data["stats"]["cash_usdc"] = round(wallet_summary["cash_usdc"], 4)
        data["stats"]["redeemable_usdc"] = round(wallet_summary["redeemable_usdc"], 4)
        data["stats"]["open_positions"] = int(wallet_summary["open_position_count"])
        data["stats"]["wallet_trade_activity_count"] = int(wallet_summary["trade_activity_count"])

    if runtime_money is not None:
        data["stats"].update(runtime_money)

    # Add open positions from poller
    open_pos = get_open_positions()
    data["open_positions"] = [
        {
            "title": p["title"],
            "slug": p["slug"],
            "outcome": p["outcome"],
            "size": p["size"],
            "avg_price": p["avg_price"],
            "current_value": p["current_value"],
            "unrealized_pnl": p["unrealized_pnl"],
            "status": p["status"],
        }
        for p in open_pos
    ]

    return data
