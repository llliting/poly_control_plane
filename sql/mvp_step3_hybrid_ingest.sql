-- Hybrid ingest mode:
-- 1) decision/trade records are persisted in Postgres
-- 2) runtime snapshots are not required
-- 3) logs are streamed in-memory via API (not stored in Postgres)

ALTER TABLE IF EXISTS decision_records
  ADD COLUMN IF NOT EXISTS market_price numeric(20,8) NULL;

ALTER TABLE IF EXISTS decision_records
  ADD COLUMN IF NOT EXISTS binance_price numeric(20,8) NULL;

ALTER TABLE IF EXISTS decision_records
  ADD COLUMN IF NOT EXISTS binance_price_change_5m numeric(20,8) NULL;

ALTER TABLE IF EXISTS decision_records
  ADD COLUMN IF NOT EXISTS danger_f_adx_3m numeric(10,6) NULL;

ALTER TABLE IF EXISTS decision_records
  ADD COLUMN IF NOT EXISTS danger_f_spread_3m numeric(10,6) NULL;

ALTER TABLE IF EXISTS decision_records
  ADD COLUMN IF NOT EXISTS danger_f_er_3m numeric(10,6) NULL;

ALTER TABLE IF EXISTS trades
  ADD COLUMN IF NOT EXISTS market_price numeric(20,8) NULL;
