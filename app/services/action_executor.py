from __future__ import annotations

import json
import shlex
import socket
import subprocess
import threading
import time
from datetime import UTC, datetime

from app.core.config import settings
from app.services.log_stream import append_log
from app.services.repository import (
    claim_next_action_request,
    complete_action_request,
    update_service_status,
)


def _iso_now() -> str:
    return datetime.now(tz=UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _parse_command_map() -> dict[str, dict[str, str]]:
    raw = (settings.action_command_map_json or "").strip()
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except Exception:
        return {}
    if not isinstance(data, dict):
        return {}

    out: dict[str, dict[str, str]] = {}
    for service_key, commands in data.items():
        if not isinstance(service_key, str) or not isinstance(commands, dict):
            continue
        row: dict[str, str] = {}
        for action in ("start", "stop", "build", "redeem", "status"):
            value = commands.get(action)
            if isinstance(value, str) and value.strip():
                row[action] = value.strip()
        if row:
            out[service_key] = row
    return out


def _runner_key() -> str:
    return settings.action_executor_runner_key or socket.gethostname()


def _status_command(commands: dict[str, str]) -> list[str] | None:
    explicit = commands.get("status")
    if explicit:
        return shlex.split(explicit)

    for candidate in (commands.get("start"), commands.get("stop"), commands.get("build")):
        if not candidate:
            continue
        parts = shlex.split(candidate)
        if parts and parts[-1] in {"start", "stop", "build", "restart"}:
            parts[-1] = "status"
            return parts
    return None


def probe_service_state(service_key: str, runner_key: str | None = None, timeout_s: float = 2.0) -> dict | None:
    if runner_key and runner_key != _runner_key():
        return None

    commands = _parse_command_map().get(service_key)
    if not commands:
        return None

    cmd = _status_command(commands)
    if not cmd:
        return None

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=max(timeout_s, 0.5),
            check=False,
        )
    except Exception:
        return None

    output = f"{proc.stdout or ''}\n{proc.stderr or ''}".strip().lower()
    if proc.returncode == 0 and "running" in output:
        process_state = "running"
        status = "healthy"
    elif proc.returncode == 0 and "stopped" in output:
        process_state = "stopped"
        status = "stopped"
    else:
        process_state = "unknown"
        status = "degraded"

    return {
        "process_state": process_state,
        "status": status,
        "can_start": process_state != "running",
        "can_stop": process_state == "running",
        "build_available": "build" in commands,
    }


class ActionExecutor:
    def __init__(self) -> None:
        self._runner_key = _runner_key()
        self._poll_s = max(settings.action_executor_poll_ms, 100) / 1000.0
        self._timeout_s = max(settings.action_executor_timeout_secs, 5)
        self._max_chars = max(settings.action_executor_max_output_chars, 256)
        self._command_map = _parse_command_map()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._run_loop, name="action-executor", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)

    def _run_loop(self) -> None:
        append_log(
            {
                "ts": _iso_now(),
                "service_key": "control_plane",
                "level": "info",
                "message": f"action_executor started runner_key={self._runner_key}",
            }
        )
        while not self._stop.is_set():
            task = claim_next_action_request(runner_key=self._runner_key)
            if not task:
                time.sleep(self._poll_s)
                continue
            self._handle_task(task)
        append_log(
            {
                "ts": _iso_now(),
                "service_key": "control_plane",
                "level": "info",
                "message": "action_executor stopped",
            }
        )

    def _handle_task(self, task: dict) -> None:
        action_id = str(task.get("action_id") or "")
        service_key = str(task.get("service_key") or "")
        action = str(task.get("action") or "")
        cmd = self._command_map.get(service_key, {}).get(action)
        if not cmd:
            msg = f"no configured command for service={service_key} action={action}"
            complete_action_request(
                action_id=action_id,
                success=False,
                exit_code=None,
                stdout_excerpt="",
                stderr_excerpt=msg,
                result_payload={"runner_key": self._runner_key},
            )
            append_log({"ts": _iso_now(), "service_key": service_key, "level": "warn", "message": msg})
            return

        append_log(
            {
                "ts": _iso_now(),
                "service_key": service_key,
                "level": "info",
                "message": f"action start id={action_id} action={action} cmd={cmd}",
            }
        )
        t0 = time.monotonic()
        try:
            proc = subprocess.run(
                shlex.split(cmd),
                capture_output=True,
                text=True,
                timeout=self._timeout_s,
                check=False,
            )
            elapsed_ms = int((time.monotonic() - t0) * 1000)
            ok = proc.returncode == 0
            stdout_excerpt = (proc.stdout or "")[: self._max_chars]
            stderr_excerpt = (proc.stderr or "")[: self._max_chars]
            complete_action_request(
                action_id=action_id,
                success=ok,
                exit_code=proc.returncode,
                stdout_excerpt=stdout_excerpt,
                stderr_excerpt=stderr_excerpt,
                result_payload={
                    "runner_key": self._runner_key,
                    "elapsed_ms": elapsed_ms,
                    "command": cmd,
                },
            )
            self._append_process_output_logs(service_key, action, proc.stdout or "", proc.stderr or "")
            if ok:
                if action == "start":
                    update_service_status(service_key=service_key, status="healthy")
                elif action == "stop":
                    update_service_status(service_key=service_key, status="stopped")
            append_log(
                {
                    "ts": _iso_now(),
                    "service_key": service_key,
                    "level": "info" if ok else "warn",
                    "message": f"action finish id={action_id} action={action} ok={ok} exit_code={proc.returncode} elapsed_ms={elapsed_ms}",
                }
            )
        except subprocess.TimeoutExpired:
            msg = f"action timeout id={action_id} action={action} timeout_s={self._timeout_s}"
            complete_action_request(
                action_id=action_id,
                success=False,
                exit_code=None,
                stdout_excerpt="",
                stderr_excerpt=msg,
                result_payload={"runner_key": self._runner_key, "command": cmd},
            )
            append_log({"ts": _iso_now(), "service_key": service_key, "level": "warn", "message": msg})
        except Exception as err:
            msg = f"action exec error id={action_id} action={action} err={err}"
            complete_action_request(
                action_id=action_id,
                success=False,
                exit_code=None,
                stdout_excerpt="",
                stderr_excerpt=msg[: self._max_chars],
                result_payload={"runner_key": self._runner_key, "command": cmd},
            )
            append_log({"ts": _iso_now(), "service_key": service_key, "level": "warn", "message": msg})

    def _append_process_output_logs(self, service_key: str, action: str, stdout: str, stderr: str) -> None:
        for level, prefix, text in (
            ("info", "stdout", stdout),
            ("warn", "stderr", stderr),
        ):
            for raw_line in text.splitlines():
                line = raw_line.strip()
                if not line:
                    continue
                append_log(
                    {
                        "ts": _iso_now(),
                        "service_key": service_key,
                        "level": level,
                        "message": f"action {action} {prefix}: {line[: self._max_chars]}",
                    }
                )
