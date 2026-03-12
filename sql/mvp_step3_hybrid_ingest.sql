-- Hybrid ingest mode:
-- 1) decision/trade records are persisted in Postgres
-- 2) runtime snapshots are not required
-- 3) logs are streamed in-memory via API (not stored in Postgres)

ALTER TABLE IF EXISTS decision_records
  ADD COLUMN IF NOT EXISTS market_price numeric(20,8) NULL;

ALTER TABLE IF EXISTS trades
  ADD COLUMN IF NOT EXISTS market_price numeric(20,8) NULL;
