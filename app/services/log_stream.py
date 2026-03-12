from __future__ import annotations

from collections import deque
from threading import Lock

_MAX_LOG_ROWS = 5000
_rows: deque[dict] = deque(maxlen=_MAX_LOG_ROWS)
_lock = Lock()


def append_log(row: dict) -> None:
    with _lock:
        _rows.append(row)


def list_logs(service_key: str = "all", limit: int = 200) -> list[dict]:
    with _lock:
        if service_key == "all":
            rows = list(_rows)
        else:
            rows = [row for row in _rows if row.get("service_key") == service_key]
    rows.sort(key=lambda row: row.get("ts", ""), reverse=True)
    return rows[:limit]
