# Live Trading Frontend Prototype

This is a monitoring MVP frontend wired to the `control-plane-api`.

## Run locally

From repo root:

```bash
cd live-trading-frontend
python3 -m http.server 8081
```

Then open:

`http://localhost:8081`

## Notes

- Ash background + white text theme
- Compact table density across all pages
- Polling-based live refresh from backend API (`/api/v1/*`)
- Pages: Overview, Service Detail, Market Monitor, Trades, Logs
- Backend/data contract: `../docs/live-trading-control-plane-spec.md`
- Default backend base URL in frontend: `http://127.0.0.1:8090/api/v1`
