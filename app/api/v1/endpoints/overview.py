from fastapi import APIRouter, Query

from app.core.config import settings
from app.services.mock_data import get_overview
from app.services.polymarket_data import fetch_wallet_summary
from app.services.repository import get_overview_from_db

router = APIRouter()


@router.get("/overview")
def overview(
    service_key: str = Query(default="all"),
    from_date: str = Query(alias="from", default="2026-03-10"),
    to_date: str = Query(alias="to", default="2026-03-12"),
) -> dict:
    try:
        data = get_overview_from_db(service_key=service_key, from_date=from_date, to_date=to_date)
        if data is not None:
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
            return data
    except Exception:
        pass
    return get_overview(service_key=service_key, from_date=from_date, to_date=to_date)
