from __future__ import annotations

import json
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import text

from app.db.session import get_engine


def _to_iso_z(value: object) -> str:
    if isinstance(value, datetime):
        return value.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    return str(value)


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


def get_service_detail_from_db(service_key: str) -> dict | None:
    engine = get_engine()
    if engine is None:
        return None

    service_query = text(
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
        WHERE service_key = :service_key
        LIMIT 1
        """
    )
    runtime_query = text(
        """
        SELECT
          status,
          signal,
          p_up,
          edge,
          traded,
          portfolio_usdc,
          position_usdc,
          cash_usdc,
          ingest_lag_ms
        FROM service_runtime_snapshots
        WHERE service_key = :service_key
        ORDER BY captured_at DESC
        LIMIT 1
        """
    )

    with engine.connect() as conn:
        service_row = conn.execute(service_query, {"service_key": service_key}).mappings().first()
        if service_row is None:
            return None
        runtime_row = conn.execute(runtime_query, {"service_key": service_key}).mappings().first()

    base_service = {
        "service_key": service_row["service_key"],
        "display_name": service_row["display_name"],
        "asset": service_row["asset"],
        "timeframe": service_row["timeframe"],
        "strategy_key": service_row["strategy_key"],
        "runner_key": service_row["runner_key"],
        "status": service_row["status"],
        "signal": "SKIP",
        "p_up": 0.5,
        "edge": 0.0,
        "traded": False,
        "git_branch": service_row["git_branch"],
        "git_commit": service_row["git_commit"],
        "model_threshold": 0.85,
        "edge_floor": 0.00,
        "edge_ceiling": 0.40,
        "portfolio_usdc": 0.0,
        "position_usdc": 0.0,
        "cash_usdc": 0.0,
    }
    if runtime_row:
        base_service.update(
            {
                "status": runtime_row["status"] or base_service["status"],
                "signal": runtime_row["signal"] or base_service["signal"],
                "p_up": float(runtime_row["p_up"] or 0),
                "edge": float(runtime_row["edge"] or 0),
                "traded": bool(runtime_row["traded"]),
                "portfolio_usdc": float(runtime_row["portfolio_usdc"] or 0),
                "position_usdc": float(runtime_row["position_usdc"] or 0),
                "cash_usdc": float(runtime_row["cash_usdc"] or 0),
            }
        )

    health = {
        "ready": base_service["status"] in {"healthy", "degraded"},
        "binance_connected": True,
        "okx_connected": True,
        "rtds_connected": True,
        "last_event_age_ms": int(runtime_row["ingest_lag_ms"] or 0) if runtime_row else 0,
        "trade_retries_10m": 0,
        "claimable_usdc": 0.0,
        "process_state": "stopped" if base_service["status"] == "stopped" else "running",
    }
    controls = {
        "can_start": base_service["status"] == "stopped",
        "can_stop": base_service["status"] in {"healthy", "degraded"},
        "allowed_actions": ["start", "stop", "restart", "redeploy"],
    }
    return {"service": base_service, "health": health, "controls": controls}


def list_decisions_from_db(service_key: str, limit: int = 50) -> list[dict] | None:
    engine = get_engine()
    if engine is None:
        return None

    query = text(
        """
        SELECT
          id,
          occurred_at,
          market_slug,
          side,
          p_up,
          threshold,
          edge,
          streak_hits,
          streak_target,
          traded,
          no_trade_reason
        FROM decision_records
        WHERE service_key = :service_key
        ORDER BY occurred_at DESC
        LIMIT :limit
        """
    )
    with engine.connect() as conn:
        rows = conn.execute(query, {"service_key": service_key, "limit": limit}).mappings().all()

    items: list[dict] = []
    for row in rows:
        items.append(
            {
                "decision_id": row["id"],
                "ts": _to_iso_z(row["occurred_at"]),
                "market_slug": row["market_slug"],
                "side": row["side"],
                "p_up": float(row["p_up"] or 0),
                "threshold": float(row["threshold"] or 0),
                "edge": float(row["edge"] or 0),
                "streak_hits": int(row["streak_hits"] or 0),
                "streak_target": int(row["streak_target"] or 0),
                "traded": bool(row["traded"]),
                "no_trade_reason": row["no_trade_reason"],
            }
        )
    return items


def list_runtime_signals_from_db(service_key: str, limit: int = 50) -> list[dict] | None:
    engine = get_engine()
    if engine is None:
        return None

    query = text(
        """
        SELECT
          captured_at,
          binance_price,
          chainlink_price,
          pm_mid,
          pm_bid,
          pm_ask,
          cl_bin_spread,
          bucket_seconds_left,
          ingest_lag_ms,
          streak_hits,
          streak_target
        FROM service_runtime_snapshots
        WHERE service_key = :service_key
        ORDER BY captured_at DESC
        LIMIT :limit
        """
    )
    with engine.connect() as conn:
        rows = conn.execute(query, {"service_key": service_key, "limit": limit}).mappings().all()

    items: list[dict] = []
    for row in rows:
        items.append(
            {
                "ts": _to_iso_z(row["captured_at"]),
                "binance_price": float(row["binance_price"] or 0),
                "chainlink_price": float(row["chainlink_price"] or 0),
                "pm_mid": float(row["pm_mid"] or 0),
                "pm_bid": float(row["pm_bid"] or 0),
                "pm_ask": float(row["pm_ask"] or 0),
                "cl_bin_spread": float(row["cl_bin_spread"] or 0),
                "bucket_seconds_left": int(row["bucket_seconds_left"] or 0),
                "ingest_lag_ms": int(row["ingest_lag_ms"] or 0),
                "streak_hits": int(row["streak_hits"] or 0),
                "streak_target": int(row["streak_target"] or 0),
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
        items.append(
            {
                "trade_id": str(row["id"]),
                "service_key": row["service_key"],
                "market_slug": row["market_slug"],
                "open_time": _to_iso_z(row["open_time"]),
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


def create_action_request(service_key: str, action: str, requested_payload: dict | None = None) -> dict | None:
    engine = get_engine()
    if engine is None:
        return None

    action_id = str(uuid4())
    payload = requested_payload or {}
    query = text(
        """
        INSERT INTO action_requests (
          id,
          service_key,
          action_type,
          requested_payload,
          status,
          requested_at
        )
        VALUES (
          :id,
          :service_key,
          :action_type,
          CAST(:requested_payload AS jsonb),
          :status,
          now()
        )
        """
    )
    with engine.begin() as conn:
        conn.execute(
            query,
            {
                "id": action_id,
                "service_key": service_key,
                "action_type": action,
                "requested_payload": json.dumps(payload),
                "status": "queued",
            },
        )

    return {
        "action_id": action_id,
        "service_key": service_key,
        "action": action,
        "status": "queued",
        "requested_at": _to_iso_z(datetime.now(tz=UTC)),
    }


def get_action_status(action_id: str) -> dict | None:
    engine = get_engine()
    if engine is None:
        return None

    query = text(
        """
        SELECT
          ar.id,
          ar.service_key,
          ar.action_type,
          ar.status,
          ar.requested_payload,
          ar.requested_at,
          ar.started_at,
          ar.finished_at,
          res.success,
          res.exit_code,
          res.stdout_excerpt,
          res.stderr_excerpt,
          res.result_payload
        FROM action_requests ar
        LEFT JOIN action_results res ON res.action_request_id = ar.id
        WHERE ar.id = :action_id
        LIMIT 1
        """
    )
    with engine.connect() as conn:
        row = conn.execute(query, {"action_id": action_id}).mappings().first()
    if row is None:
        return None

    return {
        "action_id": row["id"],
        "service_key": row["service_key"],
        "action": row["action_type"],
        "status": row["status"],
        "requested_payload": row["requested_payload"] or {},
        "requested_at": _to_iso_z(row["requested_at"]),
        "started_at": _to_iso_z(row["started_at"]) if row["started_at"] else None,
        "finished_at": _to_iso_z(row["finished_at"]) if row["finished_at"] else None,
        "result": {
            "success": row["success"],
            "exit_code": row["exit_code"],
            "stdout_excerpt": row["stdout_excerpt"],
            "stderr_excerpt": row["stderr_excerpt"],
            "result_payload": row["result_payload"] or {},
        },
    }


def insert_runtime_snapshot(payload: dict) -> dict | None:
    engine = get_engine()
    if engine is None:
        return None

    snapshot_id = str(uuid4())
    query = text(
        """
        INSERT INTO service_runtime_snapshots (
          id,
          service_key,
          captured_at,
          status,
          signal,
          p_up,
          edge,
          traded,
          portfolio_usdc,
          position_usdc,
          cash_usdc,
          binance_price,
          chainlink_price,
          pm_mid,
          pm_bid,
          pm_ask,
          cl_bin_spread,
          bucket_seconds_left,
          ingest_lag_ms,
          streak_hits,
          streak_target
        )
        VALUES (
          :id,
          :service_key,
          CAST(:captured_at AS timestamptz),
          :status,
          :signal,
          :p_up,
          :edge,
          :traded,
          :portfolio_usdc,
          :position_usdc,
          :cash_usdc,
          :binance_price,
          :chainlink_price,
          :pm_mid,
          :pm_bid,
          :pm_ask,
          :cl_bin_spread,
          :bucket_seconds_left,
          :ingest_lag_ms,
          :streak_hits,
          :streak_target
        )
        """
    )
    params = {
        "id": snapshot_id,
        "service_key": payload["service_key"],
        "captured_at": payload["captured_at"],
        "status": payload.get("status", "healthy"),
        "signal": payload.get("signal"),
        "p_up": payload.get("p_up"),
        "edge": payload.get("edge"),
        "traded": payload.get("traded"),
        "portfolio_usdc": payload.get("portfolio_usdc"),
        "position_usdc": payload.get("position_usdc"),
        "cash_usdc": payload.get("cash_usdc"),
        "binance_price": payload.get("binance_price"),
        "chainlink_price": payload.get("chainlink_price"),
        "pm_mid": payload.get("pm_mid"),
        "pm_bid": payload.get("pm_bid"),
        "pm_ask": payload.get("pm_ask"),
        "cl_bin_spread": payload.get("cl_bin_spread"),
        "bucket_seconds_left": payload.get("bucket_seconds_left"),
        "ingest_lag_ms": payload.get("ingest_lag_ms"),
        "streak_hits": payload.get("streak_hits"),
        "streak_target": payload.get("streak_target"),
    }
    with engine.begin() as conn:
        conn.execute(query, params)
    return {"snapshot_id": snapshot_id, "status": "inserted"}


def upsert_decision(payload: dict) -> dict | None:
    engine = get_engine()
    if engine is None:
        return None

    select_query = text(
        """
        SELECT id
        FROM decision_records
        WHERE service_key = :service_key
          AND market_slug = :market_slug
          AND occurred_at = CAST(:occurred_at AS timestamptz)
          AND side = :side
        LIMIT 1
        """
    )
    insert_query = text(
        """
        INSERT INTO decision_records (
          id,
          service_key,
          occurred_at,
          market_slug,
          side,
          p_up,
          threshold,
          edge,
          streak_hits,
          streak_target,
          traded,
          no_trade_reason
        )
        VALUES (
          :id,
          :service_key,
          CAST(:occurred_at AS timestamptz),
          :market_slug,
          :side,
          :p_up,
          :threshold,
          :edge,
          :streak_hits,
          :streak_target,
          :traded,
          :no_trade_reason
        )
        """
    )
    params = {
        "service_key": payload["service_key"],
        "occurred_at": payload["occurred_at"],
        "market_slug": payload["market_slug"],
        "side": payload["side"],
        "p_up": payload["p_up"],
        "threshold": payload["threshold"],
        "edge": payload["edge"],
        "streak_hits": payload["streak_hits"],
        "streak_target": payload["streak_target"],
        "traded": payload["traded"],
        "no_trade_reason": payload.get("no_trade_reason"),
    }
    with engine.begin() as conn:
        existing = conn.execute(select_query, params).mappings().first()
        if existing is not None:
            return {"decision_id": str(existing["id"]), "status": "exists"}
        decision_id = str(uuid4())
        conn.execute(insert_query, {"id": decision_id, **params})
    return {"decision_id": decision_id, "status": "inserted"}


def upsert_trade(payload: dict) -> dict | None:
    engine = get_engine()
    if engine is None:
        return None

    select_query = text(
        """
        SELECT id
        FROM trades
        WHERE service_key = :service_key
          AND market_slug = :market_slug
          AND open_time = CAST(:open_time AS timestamptz)
          AND side = :side
          AND amount_usdc = :amount_usdc
          AND entry_price = :entry_price
        LIMIT 1
        """
    )
    insert_query = text(
        """
        INSERT INTO trades (
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
        )
        VALUES (
          :id,
          :service_key,
          :market_slug,
          CAST(:open_time AS timestamptz),
          :side,
          :model_probability,
          :entry_price,
          :amount_usdc,
          :result,
          :pnl_usdc,
          :status
        )
        """
    )
    params = {
        "service_key": payload["service_key"],
        "market_slug": payload["market_slug"],
        "open_time": payload["open_time"],
        "side": payload["side"],
        "model_probability": payload["model_probability"],
        "entry_price": payload["entry_price"],
        "amount_usdc": payload["amount_usdc"],
        "result": payload["result"],
        "pnl_usdc": payload["pnl_usdc"],
        "status": payload.get("status", "settled"),
    }
    with engine.begin() as conn:
        existing = conn.execute(select_query, params).mappings().first()
        if existing is not None:
            return {"trade_id": str(existing["id"]), "status": "exists"}
        trade_id = str(uuid4())
        conn.execute(insert_query, {"id": trade_id, **params})
    return {"trade_id": trade_id, "status": "inserted"}
