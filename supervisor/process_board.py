"""Start / stop / probe the Board Flask process (sibling to Control)."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from typing import Any, Optional

import requests

from .paths import DEFAULT_BOARD_PORT, ROOT, STACK_DIR, ensure_dirs

_PID_FILE = STACK_DIR / "board.pid"
_LOG_FILE = STACK_DIR / "board.log"


def _board_port() -> int:
    return int(os.environ.get("PORT", str(DEFAULT_BOARD_PORT)))


def _board_url() -> str:
    return f"http://127.0.0.1:{_board_port()}"


def _read_pid() -> Optional[int]:
    if not _PID_FILE.is_file():
        return None
    try:
        return int(_PID_FILE.read_text(encoding="utf-8").strip())
    except ValueError:
        return None


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _http_up() -> bool:
    try:
        resp = requests.get(f"{_board_url()}/api/settings/host", timeout=1.5)
        return resp.status_code < 500
    except Exception:
        return False


def status() -> dict[str, Any]:
    pid = _read_pid()
    managed = bool(pid and _pid_alive(pid))
    http = _http_up()
    return {
        "managed": managed,
        "pid": pid if managed else None,
        "http": http,
        "running": managed or http,
        "port": _board_port(),
        "log_file": str(_LOG_FILE),
    }


def start() -> dict[str, Any]:
    ensure_dirs()
    current = status()
    if current["http"]:
        return {**current, "started": False, "message": "Board already responding"}
    if current["managed"]:
        return {**current, "started": False, "message": "Board process already managed"}

    env = os.environ.copy()
    env.setdefault("PORT", str(_board_port()))
    log = open(_LOG_FILE, "a", encoding="utf-8")
    proc = subprocess.Popen(
        [sys.executable, "-m", "server.app"],
        cwd=str(ROOT),
        env=env,
        stdout=log,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    _PID_FILE.write_text(str(proc.pid), encoding="utf-8")
    # wait briefly for listen
    for _ in range(30):
        if _http_up():
            break
        if proc.poll() is not None:
            break
        time.sleep(0.2)
    return {**status(), "started": True, "message": "Board start requested"}


def stop() -> dict[str, Any]:
    pid = _read_pid()
    if pid and _pid_alive(pid):
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            pass
        for _ in range(25):
            if not _pid_alive(pid):
                break
            time.sleep(0.2)
        if _pid_alive(pid):
            try:
                os.kill(pid, signal.SIGKILL)
            except OSError:
                pass
    if _PID_FILE.exists():
        _PID_FILE.unlink(missing_ok=True)
    return {**status(), "stopped": True}


def tail_log(lines: int = 80) -> str:
    if not _LOG_FILE.is_file():
        return ""
    text = _LOG_FILE.read_text(encoding="utf-8", errors="replace")
    parts = text.splitlines()
    return "\n".join(parts[-max(1, min(lines, 500)) :])
