# Control Plane API

FastAPI scaffold for the central backend that powers `live-trading-frontend`.

## Run

```bash
cd control-plane-api
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip setuptools wheel
pip install -e .
uvicorn app.main:app --reload --port 8090
```

Open docs:

- `http://localhost:8090/docs`

## Current status

- API routes for session, overview, services, market, trades, logs, actions
- `/services` and `/trades` can read from Postgres when `DATABASE_URL` is set
- `/services/{service_key}`, `/services/{service_key}/decisions`, `/services/{service_key}/runtime-signals` can read from Postgres if related tables exist
- `POST /services/{service_key}/actions` writes `action_requests` when DB is available
- `GET /actions/{action_id}` reads action status/result from Postgres
- Other endpoints currently return mock data aligned to `docs/live-trading-control-plane-spec.md`
- Project structure ready for Postgres + Alembic wiring

## Apply step-2 tables

```bash
PGPASSWORD='YOUR_DB_PASSWORD' psql -h 127.0.0.1 -U control_user -d control_plane -f sql/mvp_step2_tables.sql
```
