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
- Other endpoints currently return mock data aligned to `docs/live-trading-control-plane-spec.md`
- Project structure ready for Postgres + Alembic wiring
