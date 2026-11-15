"""Ollama model library for Control → Models."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import threading
import time
from typing import Any, Optional

import requests

DEFAULT_LOCAL = "http://127.0.0.1:11434"


def _base_url(raw: Optional[str] = None) -> str:
    text = (raw or os.environ.get("OLLAMA_HOST") or DEFAULT_LOCAL).strip()
    if "://" not in text:
        text = "http://" + text
    return text.rstrip("/")


def list_models(base_url: Optional[str] = None) -> dict[str, Any]:
    base = _base_url(base_url)
    try:
        resp = requests.get(f"{base}/api/tags", timeout=5)
        resp.raise_for_status()
        data = resp.json()
        models = []
        for item in data.get("models") or []:
            name = item.get("name")
            if not name:
                continue
            models.append(
                {
                    "name": name,
                    "size": item.get("size"),
                    "modified_at": item.get("modified_at"),
                    "digest": item.get("digest"),
                }
            )
        return {"ok": True, "base_url": base, "models": models, "error": None, "cli": shutil.which("ollama") is not None}
    except Exception as exc:
        return {
            "ok": False,
            "base_url": base,
            "models": [],
            "error": str(exc),
            "cli": shutil.which("ollama") is not None,
        }


# Model downloads run in the background. A large model takes far longer than any
# request should wait, so the route starts a download and the UI polls `list_pulls`.
# State lives in memory: after a Control restart it is gone, and pulling the same
# name again resumes, because Ollama keeps the parts it already has.
_pulls: dict[str, dict[str, Any]] = {}
_pulls_lock = threading.Lock()
_KEEP_FINISHED = 10


def _now() -> float:
    return time.time()


def _update(name: str, **changes: Any) -> None:
    with _pulls_lock:
        entry = _pulls.get(name)
        if entry is not None:
            entry.update(changes)


def _progress(layers: dict[str, tuple[int, int]]) -> tuple[int, int]:
    completed = sum(done for done, _ in layers.values())
    total = sum(size for _, size in layers.values())
    return completed, total


def _run_pull_http(name: str, base: str) -> bool:
    """Stream Ollama's pull. Returns False only when Ollama could not be reached at all."""
    layers: dict[str, tuple[int, int]] = {}
    try:
        resp = requests.post(
            f"{base}/api/pull",
            json={"name": name, "stream": True},
            stream=True,
            timeout=(10, 600),  # connect, then the longest quiet gap between progress lines
        )
    except requests.RequestException:
        return False
    with resp:
        if resp.status_code >= 400:
            if resp.status_code == 404:
                message = f"Ollama has no model called {name}. Check the spelling, including the part after the colon."
            else:
                try:
                    message = resp.json().get("error") or resp.text
                except ValueError:
                    message = resp.text
            _update(name, state="failed", error=(message or f"Ollama answered {resp.status_code}")[:300], finished_at=_now())
            return True
        try:
            # chunk_size=1 hands over each progress line as soon as it ends, instead of waiting
            # for 512 bytes. Ollama sends a few short lines a second, so the cost is nothing.
            for line in resp.iter_lines(chunk_size=1):
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except ValueError:
                    continue
                if event.get("error"):
                    _update(name, state="failed", error=str(event["error"])[:300], finished_at=_now())
                    return True
                status = str(event.get("status") or "")
                digest = event.get("digest")
                if digest and event.get("total"):
                    layers[digest] = (int(event.get("completed") or 0), int(event["total"]))
                completed, total = _progress(layers)
                # Bytes so far over bytes known so far. Ollama reveals layers one at a time, so
                # this can dip when a new one appears; in real models the first layer holds
                # nearly all the bytes, and an honest number beats one that sits at 99%.
                # Held under 100 until Ollama says the model is ready.
                percent = min(completed * 100 // total, 99) if total else 0
                _update(name, status=status, completed=completed, total=total, percent=percent)
                if status == "success":
                    _update(name, state="done", completed=total, percent=100, finished_at=_now())
                    return True
        except requests.RequestException as exc:
            _update(name, state="failed", error=f"The download was interrupted ({type(exc).__name__}). Pull again to resume.", finished_at=_now())
            return True
    _update(name, state="failed", error="Ollama stopped before the download finished. Pull again to resume.", finished_at=_now())
    return True


def _run_pull(name: str, base: str) -> None:
    try:
        if _run_pull_http(name, base):
            return
        # Ollama's HTTP port did not answer. A local CLI can still pull, without progress.
        if not shutil.which("ollama"):
            _update(name, state="failed", error="Ollama is not answering. Start Ollama and try again.", finished_at=_now())
            return
        _update(name, status="downloading (no progress from the command line)")
        proc = subprocess.run(
            ["ollama", "pull", name],
            capture_output=True,
            text=True,
            timeout=6 * 3600,
            check=False,
        )
        if proc.returncode == 0:
            _update(name, state="done", status="success", percent=100, finished_at=_now())
        else:
            _update(name, state="failed", error=(proc.stderr or proc.stdout or "ollama pull failed").strip()[:300], finished_at=_now())
    except Exception as exc:  # never let the thread die silently
        _update(name, state="failed", error=f"Download stopped: {exc}"[:300], finished_at=_now())


def pull_model(name: str, base_url: Optional[str] = None) -> dict[str, Any]:
    """Start downloading a model in the background. A second call for the same name joins the first."""
    name = (name or "").strip()
    if not name:
        raise ValueError("Model name is required")
    base = _base_url(base_url)
    with _pulls_lock:
        existing = _pulls.get(name)
        if existing and existing["state"] == "running":
            return {"started": False, "joined": True, "pull": dict(existing)}
        entry = {
            "name": name,
            "state": "running",
            "status": "starting",
            "completed": 0,
            "total": 0,
            "percent": 0,
            "error": None,
            "started_at": _now(),
            "finished_at": None,
        }
        _pulls[name] = entry
        finished = sorted(
            (p for p in _pulls.values() if p["state"] != "running"),
            key=lambda p: p.get("finished_at") or 0,
        )
        for old in finished[:-_KEEP_FINISHED] if len(finished) > _KEEP_FINISHED else []:
            _pulls.pop(old["name"], None)
        snapshot = dict(entry)
    threading.Thread(target=_run_pull, args=(name, base), name=f"pull-{name}", daemon=True).start()
    return {"started": True, "joined": False, "pull": snapshot}


def list_pulls() -> list[dict[str, Any]]:
    """Running downloads first, then the most recently finished."""
    with _pulls_lock:
        items = [dict(p) for p in _pulls.values()]
    items.sort(key=lambda p: (p["state"] != "running", -(p.get("finished_at") or p["started_at"])))
    return items


def delete_model(name: str, base_url: Optional[str] = None) -> dict[str, Any]:
    name = (name or "").strip()
    if not name:
        raise ValueError("Model name is required")
    base = _base_url(base_url)
    try:
        resp = requests.delete(f"{base}/api/delete", json={"name": name}, timeout=60)
        if resp.status_code < 400:
            return {"ok": True, "name": name, "via": "http"}
        # older ollama uses POST
        resp = requests.post(f"{base}/api/delete", json={"name": name}, timeout=60)
        if resp.status_code < 400:
            return {"ok": True, "name": name, "via": "http"}
    except Exception:
        pass
    if not shutil.which("ollama"):
        raise RuntimeError(f"Could not delete {name}")
    proc = subprocess.run(
        ["ollama", "rm", name],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or proc.stdout or "ollama rm failed").strip()[:800])
    return {"ok": True, "name": name, "via": "cli"}


def _board_origin(board_origin: Optional[str] = None) -> str:
    return (board_origin or f"http://127.0.0.1:{os.environ.get('PORT', '7410')}").rstrip("/")


def board_ollama_status(board_origin: Optional[str] = None) -> dict[str, Any]:
    """Read the Board's Ollama settings over HTTP."""
    origin = _board_origin(board_origin)
    try:
        resp = requests.get(f"{origin}/api/settings/ollama", timeout=5)
        data = resp.json() if resp.content else {}
        if resp.status_code >= 400:
            return {"ok": False, "error": data.get("error") or "Board is not answering."}
        return {"ok": True, **data}
    except Exception:
        return {"ok": False, "error": "Board is not answering."}


def set_board_ollama(body: dict[str, Any], board_origin: Optional[str] = None) -> dict[str, Any]:
    """Update the Board's Ollama host and/or model over HTTP."""
    origin = _board_origin(board_origin)
    payload = {k: v for k, v in (body or {}).items() if k in {"base_url", "model"} and v is not None}
    if not payload:
        raise ValueError("Nothing to update")
    try:
        resp = requests.post(f"{origin}/api/settings/ollama", json=payload, timeout=10)
        data = resp.json() if resp.content else {}
        if resp.status_code >= 400:
            raise RuntimeError(data.get("error") or "Board is not answering.")
        return data
    except RuntimeError:
        raise
    except Exception:
        raise RuntimeError("Board is not answering.") from None


def set_board_default_model(model: str, board_origin: Optional[str] = None) -> dict[str, Any]:
    """Best-effort sync of Board's saved Ollama model via Board HTTP API."""
    try:
        data = set_board_ollama({"model": model}, board_origin)
        return {"ok": True, "board": data}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
