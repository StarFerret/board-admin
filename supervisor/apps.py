"""App catalog: manifests under catalog/ + Compose files under stacks/."""

from __future__ import annotations

import json
import os
import secrets
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any, Optional

import requests

from . import process_board, store
from .paths import CATALOG_DIR, COMPOSE_DIR, ENV_DIR, ROOT, STACK_DIR, ensure_dirs

# Only these three ship in Control → Apps. Everything else stays out of the catalog.
ALLOWED_APPS = ("board", "librechat", "n8n")  # three apps and only three (owner, 2026-11-12)


def _load_manifest(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".json":
        data = json.loads(text)
    else:
        try:
            import yaml
        except ImportError as exc:
            raise RuntimeError("PyYAML is required for .yml catalog files") from exc
        data = yaml.safe_load(text) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Catalog file must be a mapping: {path.name}")
    return data


def _launchd_plist(manifest: dict) -> Optional[Path]:
    """Plist for an app the Mac installer runs natively (no Docker), if installed."""
    label = (manifest.get("launchd") or "").strip()
    if not label:
        return None
    path = Path.home() / "Library" / "LaunchAgents" / f"{label}.plist"
    return path if path.is_file() else None


def _launchd_target(manifest: dict) -> str:
    return f"gui/{os.getuid()}/{manifest['launchd'].strip()}"


def _is_board(manifest: dict) -> bool:
    return (manifest.get("id") or "").strip() == "board"


def _health_up(url: Optional[str]) -> bool:
    if not url:
        return False
    try:
        return requests.get(url, timeout=2.5).status_code < 500
    except Exception:
        return False


CATEGORIES = ["Core", "Chat", "Automation"]
STATUSES = ("ready", "beta", "planned")
_PROBE_TTL = 10.0
_probe_cache: dict[str, tuple[float, bool]] = {}


def _cached(key: str, probe) -> bool:
    """Docker probes cost a subprocess each. The Apps page asks for every app at once."""
    hit = _probe_cache.get(key)
    now = time.monotonic()
    if hit and now - hit[0] < _PROBE_TTL:
        return hit[1]
    value = bool(probe())
    _probe_cache[key] = (now, value)
    return value


def _docker_ok(args: list[str], timeout: float) -> bool:
    try:
        proc = subprocess.run(args, capture_output=True, text=True, timeout=timeout, check=False)
        return proc.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def _daemon_answers() -> bool:
    # `docker info` can exit 0 with the daemon down. An empty version means nobody answered.
    try:
        proc = subprocess.run(
            ["docker", "version", "--format", "{{.Server.Version}}"],
            capture_output=True,
            text=True,
            timeout=6,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return proc.returncode == 0 and bool(proc.stdout.strip())


def docker_available() -> bool:
    return shutil.which("docker") is not None


def compose_available() -> bool:
    if not docker_available():
        return False
    return _cached("compose", lambda: _docker_ok(["docker", "compose", "version"], 8))


def docker_running() -> bool:
    """Installed is not enough: Docker Desktop also has to be open."""
    if not compose_available():
        return False
    return _cached("daemon", _daemon_answers)


def docker_state() -> dict[str, Any]:
    installed = compose_available()
    running = docker_running()
    if running:
        message = None
    elif installed:
        message = "Docker is installed but not open. Open Docker Desktop, wait for it to finish starting, then try again."
    else:
        message = (
            "These apps run in Docker, which is not on this Mac yet. "
            "Install Docker Desktop (or OrbStack), open it once, then come back."
        )
    return {"installed": installed, "running": running, "message": message}


def _require_docker() -> None:
    state = docker_state()
    if not state["running"]:
        raise RuntimeError(state["message"])


def _status(manifest: dict) -> str:
    status = (manifest.get("status") or "ready").strip().lower()
    return status if status in STATUSES else "ready"


def _env_file(app_id: str, manifest: dict) -> Path:
    """Per app env file for Compose: generated secrets (kept forever) plus this Mac's details.

    Secrets are made once and never shown. A manifest lists them as
    `secrets: {NAME: bytes}`; the value is that many random bytes in hex.
    """
    ENV_DIR.mkdir(parents=True, exist_ok=True)
    path = ENV_DIR / f"{app_id}.env"
    values: dict[str, str] = {}
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            key, sep, value = line.partition("=")
            if sep and key.strip():
                values[key.strip()] = value.strip()
    wanted = manifest.get("secrets") or {}
    if isinstance(wanted, list):
        wanted = {name: 32 for name in wanted}
    for name, size in wanted.items():
        if not values.get(name):
            values[name] = secrets.token_hex(max(8, int(size or 32)))
    from . import health  # local import: health imports this module

    values["STARFERRET_HOST"] = health._lan_ip()
    values["STARFERRET_MODEL"] = os.environ.get("OLLAMA_MODEL") or "qwen3.8:27b"
    path.write_text("".join(f"{k}={v}\n" for k, v in sorted(values.items())), encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass
    return path


def _compose(app_id: str, manifest: dict, *args: str, timeout: float = 120) -> subprocess.CompletedProcess:
    compose_path = _compose_file(manifest)
    ensure_dirs()
    return subprocess.run(
        [
            "docker",
            "compose",
            "-p",
            _project_name(app_id),
            "--env-file",
            str(_env_file(app_id, manifest)),
            "-f",
            str(compose_path),
            *args,
        ],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
        cwd=str(STACK_DIR),
    )


def _short_error(proc: subprocess.CompletedProcess, fallback: str) -> str:
    text = (proc.stderr or proc.stdout or fallback).strip()
    lines = [line for line in text.splitlines() if line.strip()]
    return (lines[-1] if lines else fallback)[:400]


def _manifest_paths() -> list[Path]:
    CATALOG_DIR.mkdir(parents=True, exist_ok=True)
    paths = list(CATALOG_DIR.glob("*.json")) + list(CATALOG_DIR.glob("*.yml")) + list(CATALOG_DIR.glob("*.yaml"))
    return sorted({p.resolve() for p in paths}, key=lambda p: p.name)


def list_manifests() -> list[dict[str, Any]]:
    ensure_dirs()
    items = []
    for path in _manifest_paths():
        try:
            data = _load_manifest(path)
        except Exception as exc:
            items.append({"id": path.stem, "error": str(exc), "name": path.stem})
            continue
        app_id = data.get("id") or path.stem
        if app_id not in ALLOWED_APPS:
            continue
        state = store.get_app_state(app_id)
        items.append(
            {
                "id": app_id,
                "name": data.get("name") or app_id,
                "description": data.get("description") or "",
                "ports": data.get("ports") or [],
                "depends": data.get("depends") or [],
                "health": data.get("health"),
                "deep_link": bool(data.get("deep_link", True)),
                "compose": data.get("compose"),
                "category": data.get("category") or "Other",
                "status": _status(data),
                "note": data.get("note") or "",
                "homepage": data.get("homepage") or "",
                "enabled": state["enabled"],
                "desired": state["desired"],
                "runtime": status_for(app_id, data),
            }
        )
    order = {name: i for i, name in enumerate(CATEGORIES)}
    items.sort(key=lambda a: (order.get(a.get("category"), len(order)), STATUSES.index(a.get("status", "ready")), a["name"].lower()))
    return items


def board_entry() -> dict[str, Any]:
    """The Board is our own app and is always installed. It is not in catalog/
    and has no start or stop here (Control → Machine owns its lifecycle)."""
    from . import process_board

    info = process_board.status()
    return {
        "id": "board",
        "name": "Board",
        "description": "Shared folders with AI agents your team can work with together.",
        "ports": [info["port"]],
        "builtin": True,
        "runtime": {"running": bool(info["running"]), "native": True, "error": None},
    }


def get_manifest(app_id: str) -> Optional[dict]:
    for path in _manifest_paths():
        try:
            data = _load_manifest(path)
        except Exception:
            continue
        if (data.get("id") or path.stem) == app_id:
            return data
    return None


def _project_name(app_id: str) -> str:
    safe = "".join(ch if ch.isalnum() else "-" for ch in app_id).strip("-").lower()
    return f"starferret-{safe}"


def _compose_file(manifest: dict) -> Path:
    rel = (manifest.get("compose") or "").strip()
    if not rel:
        raise FileNotFoundError(f"No compose path for {manifest.get('id')}")
    path = (ROOT / rel).resolve()
    if not path.is_file():
        # also allow bare filename under stacks/
        alt = (COMPOSE_DIR / Path(rel).name).resolve()
        if alt.is_file():
            return alt
        raise FileNotFoundError(f"Compose file missing for {manifest.get('id')}: {rel}")
    return path


def status_for(app_id: str, manifest: Optional[dict] = None) -> dict[str, Any]:
    manifest = manifest or get_manifest(app_id) or {}
    state = store.get_app_state(app_id)
    base: dict[str, Any] = {
        "running": False,
        "containers": [],
        "error": None,
        "url": None,
        "docker": docker_running(),
        "native": False,
    }
    ports = manifest.get("ports") or []
    if ports:
        base["url"] = f"http://127.0.0.1:{ports[0]}"
    if _launchd_plist(manifest):
        base["native"] = True
        base["running"] = _health_up(manifest.get("health") or base["url"])
        return base
    # Dev / no installer: Board is a sibling Python process, not Compose.
    if _is_board(manifest):
        st = process_board.status()
        port = st.get("port") or (ports[0] if ports else 7410)
        base["native"] = True
        base["running"] = bool(st.get("running"))
        base["url"] = f"http://127.0.0.1:{port}"
        return base
    if not manifest.get("compose"):
        # Runs only as a service the installer sets up, and it has not been set up on this Mac.
        base["native"] = True
        base["installed"] = False
        return base
    if _status(manifest) == "planned" or not base["docker"]:
        # Not an error: the Apps page explains Docker once, at the top.
        return base
    if not state["enabled"] and state["desired"] != "running":
        return base
    try:
        proc = _compose(app_id, manifest, "ps", "--format", "json", timeout=20)
    except FileNotFoundError as exc:
        base["error"] = str(exc)
        return base
    except (OSError, subprocess.TimeoutExpired) as exc:
        base["error"] = str(exc)[:200]
        return base
    if proc.returncode != 0:
        base["error"] = _short_error(proc, "Could not read this app's status.")
        return base
    containers: list[dict] = []
    raw = (proc.stdout or "").strip()
    if raw.startswith("["):
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                containers = [c for c in parsed if isinstance(c, dict)]
        except json.JSONDecodeError:
            containers = []
    else:
        for line in raw.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(item, dict):
                containers.append(item)
    base["containers"] = [
        {
            "name": c.get("Name") or c.get("Service"),
            "state": c.get("State") or c.get("Status"),
            "status": c.get("Status"),
        }
        for c in containers
    ]
    base["running"] = any(
        str(c.get("State") or "").lower() in {"running", "up"}
        or str(c.get("Status") or "").lower().startswith("up")
        for c in containers
    )
    return base


def start_app(app_id: str) -> dict:
    if app_id not in ALLOWED_APPS:
        raise ValueError(f"Unknown app: {app_id}")
    manifest = get_manifest(app_id)
    if not manifest:
        raise ValueError(f"Unknown app: {app_id}")
    plist = _launchd_plist(manifest)
    if plist:
        domain = f"gui/{os.getuid()}"
        # bootstrap fails harmlessly when the job is already loaded
        subprocess.run(["launchctl", "bootstrap", domain, str(plist)], capture_output=True, timeout=20, check=False)
        subprocess.run(["launchctl", "kickstart", _launchd_target(manifest)], capture_output=True, timeout=20, check=False)
        store.set_app_state(app_id, enabled=True, desired="running")
        return {"app": app_id, "runtime": status_for(app_id, manifest)}
    if _is_board(manifest):
        process_board.start()
        store.set_app_state(app_id, enabled=True, desired="running")
        return {"app": app_id, "runtime": status_for(app_id, manifest)}
    if _status(manifest) == "planned":
        raise RuntimeError(f"{manifest.get('name') or app_id} is not available yet. {manifest.get('note') or ''}".strip())
    if not manifest.get("compose"):
        raise RuntimeError(
            f"{manifest.get('name') or app_id} is not set up on this Mac yet. The StarFerret installer sets it up."
        )
    _require_docker()
    try:
        # The first start downloads the app, which can take several minutes.
        proc = _compose(app_id, manifest, "up", "-d", timeout=900)
    except subprocess.TimeoutExpired:
        raise RuntimeError("The download is taking a long time. It keeps going in Docker. Check back in a few minutes.")
    if proc.returncode != 0:
        raise RuntimeError(_short_error(proc, "The app did not start."))
    store.set_app_state(app_id, enabled=True, desired="running")
    return {"app": app_id, "runtime": status_for(app_id, manifest)}


def stop_app(app_id: str) -> dict:
    if app_id not in ALLOWED_APPS:
        raise ValueError(f"Unknown app: {app_id}")
    manifest = get_manifest(app_id)
    if not manifest:
        raise ValueError(f"Unknown app: {app_id}")
    if _launchd_plist(manifest):
        subprocess.run(["launchctl", "bootout", _launchd_target(manifest)], capture_output=True, timeout=20, check=False)
        store.set_app_state(app_id, enabled=True, desired="stopped")
        return {"app": app_id, "runtime": status_for(app_id, manifest)}
    if _is_board(manifest):
        process_board.stop()
        store.set_app_state(app_id, enabled=True, desired="stopped")
        return {"app": app_id, "runtime": status_for(app_id, manifest)}
    if docker_running() and manifest.get("compose"):
        try:
            _compose(app_id, manifest, "stop", timeout=120)
        except (OSError, subprocess.TimeoutExpired, FileNotFoundError):
            pass
    store.set_app_state(app_id, enabled=True, desired="stopped")
    return {"app": app_id, "runtime": status_for(app_id, manifest)}


def update_app(app_id: str) -> dict:
    if app_id not in ALLOWED_APPS:
        raise ValueError(f"Unknown app: {app_id}")
    manifest = get_manifest(app_id)
    if not manifest:
        raise ValueError(f"Unknown app: {app_id}")
    if _is_board(manifest) or _launchd_plist(manifest):
        raise RuntimeError("This app was installed by the Mac installer. Run the installer again to update it.")
    if _status(manifest) == "planned":
        raise RuntimeError(f"{manifest.get('name') or app_id} is not available yet.")
    _require_docker()
    try:
        proc = _compose(app_id, manifest, "pull", timeout=900)
    except subprocess.TimeoutExpired:
        raise RuntimeError("The update download timed out. Try again in a few minutes.")
    if proc.returncode != 0:
        raise RuntimeError(_short_error(proc, "The update could not be downloaded."))
    return start_app(app_id)
