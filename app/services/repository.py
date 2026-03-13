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
          s.service_key,
          s.display_name,
          s.asset,
          s.timeframe,
          s.strategy_key,
          s.runner_key,
          COALESCE(r.status, s.status) AS status,
          s.git_branch,
          s.git_commit,
          r.signal,
          r.p_up,
          r.edge,
          r.traded,
          r.portfolio_usdc,
          r.position_usdc,
          r.cash_usdc,
          EXTRACT(EPOCH FROM (now() - r.captured_at))::int AS heartbeat_age_sec
        FROM services s
        LEFT JOIN LATERAL (
          SELECT
            captured_at,
            status,
            signal,
            p_up,
            edge,
            traded,
            portfolio_usdc,
            position_usdc,
            cash_usdc
          FROM service_runtime_snapshots
          WHERE service_key = s.service_key
          ORDER BY captured_at DESC
          LIMIT 1
        ) r ON TRUE
        ORDER BY s.service_key ASC
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
                "signal": row["signal"] or "SKIP",
                "p_up": float(row["p_up"] or 0.5),
                "edge": float(row["edge"] or 0.0),
                "traded": bool(row["traded"]),
                "portfolio_usdc": float(row["portfolio_usdc"] or 0.0),
                "position_usdc": float(row["position_usdc"] or 0.0),
                "cash_usdc": float(row["cash_usdc"] or 0.0),
                "git_branch": row["git_branch"],
                "git_commit": row["git_commit"],
                "heartbeat_age_sec": max(int(row["heartbeat_age_sec"] or 0), 0),
                "model_threshold": 0.85,
                "edge_floor": 0.00,
                "edge_ceiling": 0.40,
            }
        )
    return items


def get_overview_from_db(service_key: str, from_date: str, to_date: str) -> dict | None:
    engine = get_engine()
    if engine is None:
        return None

    services = list_services_from_db()
    if services is None:
        return None

    selected_services = services if service_key == "all" else [s for s in services if s["service_key"] == service_key]
    if not selected_services and service_key != "all":
        return None

    if service_key == "all":
        trade_query = text(
            """
            SELECT
              open_time,
              pnl_usdc,
              result,
              service_key
            FROM trades
            WHERE open_time >= CAST(:from_ts AS timestamptz)
              AND open_time < CAST(:to_ts AS timestamptz) + interval '1 day'
            ORDER BY open_time ASC
            """
        )
        trade_params = {"from_ts": from_date, "to_ts": to_date}
    else:
        trade_query = text(
            """
            SELECT
              open_time,
              pnl_usdc,
              result,
              service_key
            FROM trades
            WHERE service_key = :service_key
              AND open_time >= CAST(:from_ts AS timestamptz)
              AND open_time < CAST(:to_ts AS timestamptz) + interval '1 day'
            ORDER BY open_time ASC
            """
        )
        trade_params = {"service_key": service_key, "from_ts": from_date, "to_ts": to_date}

    with engine.connect() as conn:
        trade_rows = conn.execute(trade_query, trade_params).mappings().all()

    total_pnl = 0.0
    wins = 0
    losses = 0
    cumulative_pnl_curve = [{"ts": f"{from_date}T00:00:00Z", "value_usdc": 0.0}]
    for row in trade_rows:
        pnl = float(row["pnl_usdc"] or 0.0)
        total_pnl += pnl
        if pnl > 0:
            wins += 1
        elif pnl < 0:
            losses += 1
        cumulative_pnl_curve.append({"ts": _to_iso_z(row["open_time"]), "value_usdc": round(total_pnl, 6)})

    trade_count = wins + losses
    avg_pnl = total_pnl / trade_count if trade_count else 0.0
    services_healthy = sum(1 for s in services if s["status"] == "healthy")
    open_alerts = sum(1 for s in services if s["status"] not in {"healthy", "stopped"})

    return {
        "stats": {
            "runners_online": len({s["runner_key"] for s in services if s["status"] != "stopped"}),
            "runners_total": len({s["runner_key"] for s in services}),
            "services_healthy": services_healthy,
            "services_total": len(services),
            "pnl_today_usdc": round(total_pnl, 4),
            "open_alerts": open_alerts,
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
            "portfolio_curve": [],
            "cumulative_pnl_curve": cumulative_pnl_curve,
        },
        "incidents": [],
    }


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
        "allowed_actions": ["start", "stop", "build", "restart", "redeploy"],
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
          market_price,
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
                "market_price": float(row["market_price"] or 0) if row["market_price"] is not None else None,
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
              market_price,
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
              market_price,
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
                "market_price": float(row["market_price"] or 0) if row["market_price"] is not None else None,
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


def claim_next_action_request(runner_key: str | None = None) -> dict | None:
    engine = get_engine()
    if engine is None:
        return None

    if runner_key:
        query = text(
            """
            WITH next_action AS (
              SELECT ar.id
              FROM action_requests ar
              JOIN services s ON s.service_key = ar.service_key
              WHERE ar.status = 'queued'
                AND s.runner_key = :runner_key
              ORDER BY ar.requested_at ASC
              FOR UPDATE SKIP LOCKED
              LIMIT 1
            )
            UPDATE action_requests ar
            SET status = 'running',
                started_at = now()
            FROM next_action na
            WHERE ar.id = na.id
            RETURNING ar.id, ar.service_key, ar.action_type, ar.requested_payload, ar.requested_at
            """
        )
        params = {"runner_key": runner_key}
    else:
        query = text(
            """
            WITH next_action AS (
              SELECT ar.id
              FROM action_requests ar
              WHERE ar.status = 'queued'
              ORDER BY ar.requested_at ASC
              FOR UPDATE SKIP LOCKED
              LIMIT 1
            )
            UPDATE action_requests ar
            SET status = 'running',
                started_at = now()
            FROM next_action na
            WHERE ar.id = na.id
            RETURNING ar.id, ar.service_key, ar.action_type, ar.requested_payload, ar.requested_at
            """
        )
        params = {}

    with engine.begin() as conn:
        row = conn.execute(query, params).mappings().first()
    if row is None:
        return None
    return {
        "action_id": str(row["id"]),
        "service_key": row["service_key"],
        "action": row["action_type"],
        "requested_payload": row["requested_payload"] or {},
        "requested_at": _to_iso_z(row["requested_at"]),
    }


def complete_action_request(
    action_id: str,
    success: bool,
    exit_code: int | None,
    stdout_excerpt: str,
    stderr_excerpt: str,
    result_payload: dict | None = None,
) -> None:
    engine = get_engine()
    if engine is None:
        return

    update_request = text(
        """
        UPDATE action_requests
        SET status = :status,
            finished_at = now()
        WHERE id = :action_id
        """
    )
    upsert_result = text(
        """
        INSERT INTO action_results (
          action_request_id,
          success,
          exit_code,
          stdout_excerpt,
          stderr_excerpt,
          result_payload,
          created_at
        )
        VALUES (
          :action_id,
          :success,
          :exit_code,
          :stdout_excerpt,
          :stderr_excerpt,
          CAST(:result_payload AS jsonb),
          now()
        )
        ON CONFLICT (action_request_id) DO UPDATE
        SET success = EXCLUDED.success,
            exit_code = EXCLUDED.exit_code,
            stdout_excerpt = EXCLUDED.stdout_excerpt,
            stderr_excerpt = EXCLUDED.stderr_excerpt,
            result_payload = EXCLUDED.result_payload,
            created_at = now()
        """
    )
    with engine.begin() as conn:
        conn.execute(
            update_request,
            {
                "action_id": action_id,
                "status": "succeeded" if success else "failed",
            },
        )
        conn.execute(
            upsert_result,
            {
                "action_id": action_id,
                "success": success,
                "exit_code": exit_code,
                "stdout_excerpt": stdout_excerpt,
                "stderr_excerpt": stderr_excerpt,
                "result_payload": json.dumps(result_payload or {}),
            },
        )


def update_service_status(service_key: str, status: str) -> None:
    engine = get_engine()
    if engine is None:
        return

    query = text(
        """
        UPDATE services
        SET status = :status
        WHERE service_key = :service_key
        """
    )
    with engine.begin() as conn:
        conn.execute(query, {"service_key": service_key, "status": status})


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
          market_price,
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
          :market_price,
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
        "market_price": payload.get("market_price"),
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
          market_price,
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
          :market_price,
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
        "market_price": payload.get("market_price"),
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
