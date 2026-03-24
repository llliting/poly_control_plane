CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS service_runtime_snapshots (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  service_key text NOT NULL REFERENCES services(service_key),
  captured_at timestamptz NOT NULL DEFAULT now(),
  status text NOT NULL DEFAULT 'healthy',
  signal text NULL,
  p_up numeric(8,6) NULL,
  edge numeric(10,6) NULL,
  traded boolean NULL,
  portfolio_usdc numeric(20,8) NULL,
  position_usdc numeric(20,8) NULL,
  cash_usdc numeric(20,8) NULL,
  binance_price numeric(20,8) NULL,
  chainlink_price numeric(20,8) NULL,
  pm_mid numeric(10,6) NULL,
  pm_bid numeric(10,6) NULL,
  pm_ask numeric(10,6) NULL,
  cl_bin_spread numeric(20,8) NULL,
  bucket_seconds_left integer NULL,
  ingest_lag_ms integer NULL,
  streak_hits smallint NULL,
  streak_target smallint NULL
);
CREATE INDEX IF NOT EXISTS idx_runtime_service_captured
ON service_runtime_snapshots(service_key, captured_at DESC);

CREATE TABLE IF NOT EXISTS decision_records (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  service_key text NOT NULL REFERENCES services(service_key),
  occurred_at timestamptz NOT NULL,
  market_slug text NOT NULL,
  side text NOT NULL,
  p_up numeric(8,6) NOT NULL,
  threshold numeric(8,6) NOT NULL,
  edge numeric(10,6) NOT NULL,
  streak_hits smallint NOT NULL,
  streak_target smallint NOT NULL,
  traded boolean NOT NULL,
  market_price numeric(20,8) NULL,
  binance_price numeric(20,8) NULL,
  binance_price_change_5m numeric(20,8) NULL,
  danger_f_adx_3m numeric(10,6) NULL,
  danger_f_spread_3m numeric(10,6) NULL,
  danger_f_er_3m numeric(10,6) NULL,
  no_trade_reason text NULL
);
CREATE INDEX IF NOT EXISTS idx_decisions_service_time
ON decision_records(service_key, occurred_at DESC);

CREATE TABLE IF NOT EXISTS action_requests (
  id uuid PRIMARY KEY,
  service_key text NOT NULL REFERENCES services(service_key),
  action_type text NOT NULL,
  requested_payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  status text NOT NULL,
  requested_at timestamptz NOT NULL DEFAULT now(),
  started_at timestamptz NULL,
  finished_at timestamptz NULL
);
CREATE INDEX IF NOT EXISTS idx_action_requests_service_time
ON action_requests(service_key, requested_at DESC);
CREATE INDEX IF NOT EXISTS idx_action_requests_status
ON action_requests(status);

CREATE TABLE IF NOT EXISTS action_results (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  action_request_id uuid NOT NULL UNIQUE REFERENCES action_requests(id),
  success boolean NULL,
  exit_code integer NULL,
  stdout_excerpt text NULL,
  stderr_excerpt text NULL,
  result_payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);
