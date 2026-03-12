from __future__ import annotations

from sqlalchemy import text

from app.db.session import get_engine


def list_services_from_db() -> list[dict] | None:
    engine = get_engine()
    if engine is None:
        return None

    query = text(
        """
        SELECT
          service_key,
          display_name,
          asset,
          timeframe,
          strategy_key,
          runner_key,
          status,
          git_branch,
          git_commit
        FROM services
        ORDER BY service_key ASC
        """
    )
    with engine.connect() as conn:
        rows = conn.execute(query).mappings().all()

    items: list[dict] = []
    for row in rows:
        items.append(
            {
                "service_key": row["service_key"],
                "display_name": row["display_name"],
                "asset": row["asset"],
                "timeframe": row["timeframe"],
                "strategy_key": row["strategy_key"],
                "runner_key": row["runner_key"],
                "status": row["status"],
                "signal": "SKIP",
                "p_up": 0.5,
                "edge": 0.0,
                "traded": False,
                "portfolio_usdc": 0.0,
                "position_usdc": 0.0,
                "cash_usdc": 0.0,
                "git_branch": row["git_branch"],
                "git_commit": row["git_commit"],
                "heartbeat_age_sec": 0,
                "model_threshold": 0.85,
                "edge_floor": 0.00,
                "edge_ceiling": 0.40,
            }
        )
    return items


def list_trades_from_db(
    service_key: str = "all",
    limit: int = 200,
    sort_dir: str = "desc",
) -> list[dict] | None:
    engine = get_engine()
    if engine is None:
        return None

    order = "ASC" if sort_dir.lower() == "asc" else "DESC"
    if service_key == "all":
        query = text(
            f"""
            SELECT
              id,
              service_key,
              market_slug,
              open_time,
              side,
              model_probability,
              entry_price,
              amount_usdc,
              result,
              pnl_usdc,
              status
            FROM trades
            ORDER BY open_time {order}
            LIMIT :limit
            """
        )
        params = {"limit": limit}
    else:
        query = text(
            f"""
            SELECT
              id,
              service_key,
              market_slug,
              open_time,
              side,
              model_probability,
              entry_price,
              amount_usdc,
              result,
              pnl_usdc,
              status
            FROM trades
            WHERE service_key = :service_key
            ORDER BY open_time {order}
            LIMIT :limit
            """
        )
        params = {"service_key": service_key, "limit": limit}

    with engine.connect() as conn:
        rows = conn.execute(query, params).mappings().all()

    items: list[dict] = []
    for row in rows:
        amount = float(row["amount_usdc"] or 0)
        pnl = float(row["pnl_usdc"] or 0)
        pnl_pct = (pnl / amount) * 100.0 if amount else 0.0
        open_time = row["open_time"]
        if hasattr(open_time, "isoformat"):
            open_time = open_time.isoformat().replace("+00:00", "Z")

        items.append(
            {
                "trade_id": str(row["id"]),
                "service_key": row["service_key"],
                "market_slug": row["market_slug"],
                "open_time": open_time,
                "side": row["side"],
                "model_probability": float(row["model_probability"] or 0),
                "entry_price": float(row["entry_price"] or 0),
                "amount_usdc": amount,
                "result": row["result"],
                "pnl_usdc": pnl,
                "pnl_pct": pnl_pct,
                "status": row["status"],
            }
        )
    return items

