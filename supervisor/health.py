"""Machine + stack health probes for Control → Machine."""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
from pathlib import Path
from typing import Any

import requests

from . import apps, process_board
from .paths import DATA_DIR, DEFAULT_BOARD_PORT, ROOT


def _disk_usage(path: Path) -> dict[str, Any]:
    usage = shutil.disk_usage(path)
    return {
        "path": str(path),
        "total_gb": round(usage.total / (1024**3), 2),
        "used_gb": round(usage.used / (1024**3), 2),
        "free_gb": round(usage.free / (1024**3), 2),
        "percent_used": round(100 * usage.used / usage.total, 1) if usage.total else 0,
    }


def _ollama_probe() -> dict[str, Any]:
    base = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/")
    if "://" not in base:
        base = "http://" + base
    try:
        resp = requests.get(f"{base}/api/tags", timeout=2.5)
        resp.raise_for_status()
        data = resp.json()
        models = [m.get("name") for m in data.get("models", []) if m.get("name")]
        return {"reachable": True, "base_url": base, "models": models, "error": None}
    except Exception as exc:
        return {"reachable": False, "base_url": base, "models": [], "error": str(exc)}


def _lan_ip() -> str:
    override = (os.environ.get("STARFERRET_HOST") or "").strip()
    if override:
        return override
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.connect(("8.8.8.8", 80))
        ip = sock.getsockname()[0]
        sock.close()
        return ip
    except OSError:
        return "127.0.0.1"


def _metal_hint() -> dict[str, Any]:
    """Best-effort Apple Silicon memory pressure via `memory_pressure` / sysctl."""
    out: dict[str, Any] = {"platform": os.uname().sysname if hasattr(os, "uname") else "unknown"}
    try:
        proc = subprocess.run(
            ["sysctl", "-n", "hw.memsize"],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
        if proc.returncode == 0 and proc.stdout.strip().isdigit():
            out["ram_gb"] = round(int(proc.stdout.strip()) / (1024**3), 1)
    except (OSError, subprocess.TimeoutExpired):
        pass
    try:
        proc = subprocess.run(
            ["sysctl", "-n", "machdep.cpu.brand_string"],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            out["cpu"] = proc.stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        pass
    return out


def snapshot() -> dict[str, Any]:
    board_port = int(os.environ.get("PORT", str(DEFAULT_BOARD_PORT)))
    lan = _lan_ip()
    return {
        "lan_ip": lan,
        "board": {
            **process_board.status(),
            "url": f"http://{lan}:{board_port}",
            "local_url": f"http://127.0.0.1:{board_port}",
        },
        "ollama": _ollama_probe(),
        "docker": {
            "available": apps.docker_available(),
            "compose": apps.compose_available(),
            "running": apps.docker_running(),
        },
        "disk": _disk_usage(DATA_DIR if DATA_DIR.exists() else ROOT),
        "machine": _metal_hint(),
        "apps": apps.list_manifests(),
    }
