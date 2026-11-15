"""Live utilization for Control → Overview: CPU, memory, GPU (Metal), loaded models.

Everything here uses tools that ship with macOS and need no sudo:
`ps`, `vm_stat`, `sysctl`, `ioreg`, `system_profiler`. No extra dependency.
A background thread samples every few seconds so the UI can draw a short history.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import threading
import time
from collections import deque
from typing import Any, Optional

import requests

# The GPU counts as "answering" above this. Model work drives it near 100; a screen alone stays well below.
BUSY_GPU_PERCENT = 60
SAMPLE_SECONDS = 5
HISTORY_POINTS = 120  # 10 minutes at 5 seconds

_history: deque = deque(maxlen=HISTORY_POINTS)
_lock = threading.Lock()
_thread: Optional[threading.Thread] = None
_static: Optional[dict[str, Any]] = None
# Set by the capacity test so its own load is not recorded as people using the AI.
recording_paused = False


def _run(cmd: list[str], timeout: float = 4) -> str:
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return proc.stdout if proc.returncode == 0 else ""


def _sysctl(name: str) -> str:
    return _run(["sysctl", "-n", name], timeout=3).strip()


def _int(text: str, default: int = 0) -> int:
    try:
        return int(text)
    except (TypeError, ValueError):
        return default


def _ollama_base() -> str:
    base = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/")
    return base if "://" in base else "http://" + base


def static_info() -> dict[str, Any]:
    """Facts about this Mac that do not change while Control runs. Cached."""
    global _static
    if _static is not None:
        return _static
    info: dict[str, Any] = {
        "chip": _sysctl("machdep.cpu.brand_string") or None,
        "arch": os.uname().machine if hasattr(os, "uname") else None,
        "cpu_cores": _int(_sysctl("hw.ncpu")) or (os.cpu_count() or 0),
        "performance_cores": _int(_sysctl("hw.perflevel0.physicalcpu")) or None,
        "efficiency_cores": _int(_sysctl("hw.perflevel1.physicalcpu")) or None,
        "ram_gb": round(_int(_sysctl("hw.memsize")) / (1024**3), 1) or None,
        # 1 means this process runs under Rosetta, which cannot use the GPU properly.
        "rosetta": _sysctl("sysctl.proc_translated") == "1",
        "gpu_name": None,
        "gpu_cores": None,
        "metal": None,
    }
    raw = _run(["system_profiler", "SPDisplaysDataType", "-json"], timeout=10)
    try:
        for gpu in json.loads(raw).get("SPDisplaysDataType", []):
            if gpu.get("sppci_device_type") != "spdisplays_gpu":
                continue
            info["gpu_name"] = gpu.get("sppci_model") or gpu.get("_name")
            info["gpu_cores"] = _int(gpu.get("sppci_cores")) or None
            family = gpu.get("spdisplays_mtlgpufamilysupport") or ""
            match = re.search(r"metal(\d+)", family)
            info["metal"] = f"Metal {match.group(1)}" if match else ("Metal" if family else None)
            break
    except (ValueError, AttributeError):
        pass
    info["apple_silicon"] = info["arch"] == "arm64" and not info["rosetta"]
    _static = info
    return info


def _cpu_percent(cores: int) -> Optional[float]:
    out = _run(["ps", "-A", "-o", "%cpu="])
    if not out:
        return None
    total = 0.0
    for line in out.split():
        try:
            total += float(line)
        except ValueError:
            continue
    return round(min(100.0, total / max(1, cores)), 1)


def _memory() -> dict[str, Any]:
    total = _int(_sysctl("hw.memsize"))
    out = _run(["vm_stat"])
    page = 16384
    match = re.search(r"page size of (\d+) bytes", out)
    if match:
        page = int(match.group(1))
    pages: dict[str, int] = {}
    for line in out.splitlines():
        key, _, value = line.partition(":")
        value = value.strip().rstrip(".")
        if value.isdigit():
            pages[key.strip().strip('"')] = int(value)
    # Same sum Activity Monitor calls "Memory Used": app memory + wired + compressed.
    used = (
        pages.get("Anonymous pages", pages.get("Pages active", 0))
        + pages.get("Pages wired down", 0)
        + pages.get("Pages occupied by compressor", 0)
    ) * page
    used = min(used, total) if total else used
    level = _int(_sysctl("kern.memorystatus_vm_pressure_level"), 1)
    return {
        "total_gb": round(total / (1024**3), 1) if total else None,
        "used_gb": round(used / (1024**3), 1),
        "percent": round(100 * used / total, 1) if total else None,
        "pressure": {1: "normal", 2: "warning", 4: "critical"}.get(level, "normal"),
    }


def _gpu() -> dict[str, Any]:
    """GPU load from the Apple graphics driver. Works without sudo on Apple silicon."""
    out = _run(["ioreg", "-r", "-d", "1", "-w", "0", "-c", "IOAccelerator"])
    match = re.search(r'"PerformanceStatistics" = \{([^}]*)\}', out)
    if not match:
        return {"available": False, "percent": None, "memory_gb": None}
    stats = dict(re.findall(r'"([^"]+)"=(\d+)', match.group(1)))
    return {
        "available": True,
        "percent": _int(stats.get("Device Utilization %")),
        "memory_gb": round(_int(stats.get("In use system memory")) / (1024**3), 2),
    }


def loaded_models() -> dict[str, Any]:
    """Models Ollama has in memory now, and how much of each sits on the GPU."""
    try:
        resp = requests.get(f"{_ollama_base()}/api/ps", timeout=2.5)
        resp.raise_for_status()
        raw = resp.json().get("models") or []
    except Exception as exc:
        return {"reachable": False, "models": [], "error": str(exc)[:200]}
    models = []
    for item in raw:
        size = _int(item.get("size"))
        vram = _int(item.get("size_vram"))
        details = item.get("details") or {}
        models.append(
            {
                "name": item.get("name") or item.get("model"),
                "size_gb": round(size / (1024**3), 1),
                "gpu_percent": round(100 * vram / size) if size else None,
                "parameters": details.get("parameter_size"),
                "quantization": details.get("quantization_level"),
                "context": item.get("context_length"),
                "expires_at": item.get("expires_at"),
            }
        )
    return {"reachable": True, "models": models, "error": None}


def metal_report() -> dict[str, Any]:
    """Plain answer to "is the model really running on the Mac's GPU?"."""
    info = static_info()
    ps = loaded_models()
    problems: list[str] = []
    if info.get("arch") != "arm64":
        problems.append("This is not an Apple silicon Mac, so models cannot use Metal here.")
    if info.get("rosetta"):
        problems.append("StarFerret is running under Rosetta. Reinstall it natively so models can use the GPU.")
    if not info.get("metal"):
        problems.append("macOS did not report a Metal GPU.")
    for model in ps["models"]:
        pct = model.get("gpu_percent")
        if pct is not None and pct < 100:
            problems.append(
                f"{model['name']} is only {pct}% on the GPU. The rest runs on the CPU and will be slow. "
                "Use a smaller model or close other heavy apps."
            )
    if not ps["reachable"]:
        state = "unknown"
        summary = "The model runtime is not running, so GPU use cannot be checked yet."
    elif problems:
        state = "problem"
        summary = problems[0]
    elif not ps["models"]:
        state = "idle"
        summary = "No model is loaded right now. Send one message, then check again."
    else:
        state = "ok"
        summary = "Every loaded model is fully on the GPU through Metal."
    return {
        "state": state,
        "summary": summary,
        "problems": problems,
        "gpu_name": info.get("gpu_name"),
        "gpu_cores": info.get("gpu_cores"),
        "metal": info.get("metal"),
        "apple_silicon": info.get("apple_silicon"),
        "runtime_reachable": ps["reachable"],
        "models": ps["models"],
    }


def sample() -> dict[str, Any]:
    info = static_info()
    load = os.getloadavg() if hasattr(os, "getloadavg") else (0.0, 0.0, 0.0)
    return {
        "at": int(time.time()),
        "cpu": {"percent": _cpu_percent(info.get("cpu_cores") or 1), "load_1m": round(load[0], 2)},
        "memory": _memory(),
        "gpu": _gpu(),
    }


def _people_on_board() -> Optional[int]:
    port = os.environ.get("PORT", "7410")
    try:
        return int(requests.get(f"http://127.0.0.1:{port}/api/presence", timeout=1.5).json().get("count") or 0)
    except Exception:
        return None


def _loop() -> None:
    from . import store  # local import keeps this module usable without the database

    people: Optional[int] = None
    tick = 0
    while True:
        try:
            point = sample()
            with _lock:
                _history.append(point)
            if tick % 6 == 0:  # twice a minute is plenty for a head count
                people = _people_on_board()
            tick += 1
            gpu = point["gpu"]
            if gpu["available"] and not recording_paused:
                store.record_load(point["at"], (gpu["percent"] or 0) >= BUSY_GPU_PERCENT, people)
        except Exception:
            pass
        time.sleep(SAMPLE_SECONDS)


def ensure_sampler() -> None:
    global _thread
    with _lock:
        if _thread and _thread.is_alive():
            return
        _thread = threading.Thread(target=_loop, name="starferret-metrics", daemon=True)
        _thread.start()


def snapshot() -> dict[str, Any]:
    """Current numbers plus up to ten minutes of history for the charts."""
    ensure_sampler()
    with _lock:
        points = list(_history)
    now = points[-1] if points else sample()
    return {
        "machine": static_info(),
        "now": now,
        "metal": metal_report(),
        "sample_seconds": SAMPLE_SECONDS,
        "history": [
            {
                "at": p["at"],
                "cpu": p["cpu"]["percent"],
                "memory": p["memory"]["percent"],
                "gpu": p["gpu"]["percent"],
            }
            for p in points
        ],
    }
