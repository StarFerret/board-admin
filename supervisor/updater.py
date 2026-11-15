"""One button updates for Control → Updates.

It works the way a container update does, without needing Docker:

- `~/.starferret/app` is the program (the "image"). An update replaces the whole folder.
- `~/.starferret/data` is everything the customer made (the "volume"). An update never touches it.
- `~/.starferret/app.previous` is the last program folder, kept so one click goes back.

Steps: download the new bundle, unpack it beside the running one, check it is
complete, install any new Python packages, then hand over to a small detached
script. The script swaps the folders, restarts Board and Control, and waits for
them to answer. If they do not come back it swaps the old folder in again and
restarts. The script is separate because Control cannot restart itself and
keep watching.

Only an installed copy (running from `~/.starferret/app`) can update this way.
A source checkout is updated with git by whoever owns it.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tarfile
import threading
import time
from pathlib import Path
from typing import Any, Optional

import requests

from .paths import DEFAULT_BOARD_PORT, ROOT

REPO = "StarFerret/board-admin"
ASSET = "starferret-macos.tar.gz"
HOME = Path(os.environ.get("STARFERRET_HOME") or Path.home() / ".starferret")
APP = HOME / "app"
NEW = HOME / "app.new"
PREVIOUS = HOME / "app.previous"
RESULT = HOME / "update-result.json"
SCRIPT = HOME / "update.sh"
LOG = HOME / "logs" / "update.log"
LABELS = ("com.starferret.supervisor", "com.starferret.board")

_state: dict[str, Any] = {"running": False, "step": "", "error": None}
_available: Optional[dict[str, Any]] = None
_lock = threading.Lock()


def _version_of(folder: Path) -> Optional[str]:
    try:
        return (folder / "VERSION").read_text(encoding="utf-8").strip()[:40] or None
    except OSError:
        return None


def _clean(version: Optional[str]) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "", version or "")[:40] or "unknown"


def installed() -> bool:
    try:
        return ROOT.resolve() == APP.resolve()
    except OSError:
        return False


def _override() -> Optional[str]:
    """A bundle path or URL to use instead of GitHub. For tests and private mirrors."""
    return (os.environ.get("STARFERRET_UPDATE_SOURCE") or "").strip() or None


def _set(**changes: Any) -> None:
    with _lock:
        _state.update(changes)


def info() -> dict[str, Any]:
    last = None
    try:
        last = json.loads(RESULT.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        pass
    with _lock:
        state = dict(_state)
        available = dict(_available) if _available else None
    current = _version_of(ROOT)
    return {
        "can_update": installed(),
        "version": current or "development copy",
        "available": available,
        "update_ready": bool(available and available.get("version") and available["version"] != current),
        "previous": _version_of(PREVIOUS) if PREVIOUS.is_dir() else None,
        "can_go_back": installed() and PREVIOUS.is_dir(),
        "last": last,
        "busy": state,
    }


def check() -> dict[str, Any]:
    """Ask what the newest version is. Downloads nothing."""
    global _available
    source = _override()
    try:
        if source and not source.startswith("http"):
            with tarfile.open(source) as bundle:
                member = next((m for m in bundle.getmembers() if m.name.endswith("/VERSION") and m.name.count("/") == 1), None)
                version = bundle.extractfile(member).read().decode().strip() if member else None
            found = {"version": version or "unknown", "url": source, "notes": ""}
        elif source:
            found = {"version": "unknown", "url": source, "notes": ""}
        else:
            resp = requests.get(f"https://api.github.com/repos/{REPO}/releases/latest", timeout=10)
            if resp.status_code == 404:
                raise RuntimeError("No update has been published yet.")
            resp.raise_for_status()
            data = resp.json()
            asset = next((a for a in data.get("assets") or [] if a.get("name") == ASSET), None)
            if not asset:
                raise RuntimeError("The newest release has no Mac bundle yet. Try again later.")
            found = {
                "version": (data.get("tag_name") or "").lstrip("v") or "unknown",
                "url": asset["browser_download_url"],
                "notes": (data.get("body") or "").strip()[:2000],
            }
    except RuntimeError:
        raise
    except (requests.RequestException, OSError, tarfile.TarError, ValueError):
        raise RuntimeError("Could not check for updates. Check this Mac's internet connection and try again.")
    found["checked_at"] = int(time.time())
    with _lock:
        _available = found
    return info()


def _fetch(url: str, target: Path) -> None:
    if not url.startswith("http"):
        shutil.copyfile(url, target)
        return
    with requests.get(url, stream=True, timeout=30) as resp:
        resp.raise_for_status()
        with open(target, "wb") as out:
            for chunk in resp.iter_content(1 << 16):
                out.write(chunk)


def _unpack(bundle_path: Path) -> None:
    """Unpack into app.new, dropping the bundle's single top folder."""
    shutil.rmtree(NEW, ignore_errors=True)
    staging = HOME / "app.unpack"
    shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(parents=True)
    with tarfile.open(bundle_path) as bundle:
        bundle.extractall(staging, filter="data")  # refuses paths that escape the folder
    tops = [p for p in staging.iterdir() if p.is_dir()]
    if len(tops) != 1:
        raise RuntimeError("The update file is not a StarFerret bundle.")
    tops[0].rename(NEW)
    shutil.rmtree(staging, ignore_errors=True)
    for needed in (
        "server/app.py",
        "supervisor/app.py",
        "web/dist/index.html",
        "control-web/dist/index.html",
        "server/requirements.txt",
    ):
        if not (NEW / needed).is_file():
            raise RuntimeError("The update file is incomplete. Nothing was changed.")


def _install_packages() -> None:
    new_reqs = (NEW / "server" / "requirements.txt").read_text(encoding="utf-8")
    try:
        old_reqs = (ROOT / "server" / "requirements.txt").read_text(encoding="utf-8")
    except OSError:
        old_reqs = ""
    if new_reqs == old_reqs:
        return
    uv = shutil.which("uv") or str(Path.home() / ".local" / "bin" / "uv")
    import sys

    proc = subprocess.run(
        [uv, "pip", "install", "--quiet", "--python", sys.executable, "-r", str(NEW / "server" / "requirements.txt")],
        capture_output=True,
        text=True,
        timeout=600,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError("The update needs new components that could not be installed. Nothing was changed.")


def _restart_command() -> str:
    custom = (os.environ.get("STARFERRET_RESTART_CMD") or "").strip()  # test hook
    if custom:
        return custom
    domain = f"gui/{os.getuid()}"
    return "; ".join(f"launchctl kickstart -k {domain}/{label}" for label in LABELS)


def _hand_over(mode: str, from_version: str, to_version: str) -> None:
    """Write and launch the detached script that swaps folders and restarts the services."""
    port = os.environ.get("PORT", str(DEFAULT_BOARD_PORT))
    LOG.parent.mkdir(parents=True, exist_ok=True)
    script = f"""#!/bin/bash
# Written by Control. Swaps the program folder and restarts StarFerret.
H="{HOME}"
HEALTH="http://127.0.0.1:{port}/api/control/health"
restart() {{ {_restart_command()}; }}
came_back() {{
  for i in $(seq 1 45); do
    sleep 2
    [ "$(curl -s -o /dev/null -m 3 -w '%{{http_code}}' "$HEALTH")" = "200" ] && return 0
  done
  return 1
}}
result() {{ printf '{{"result":"%s","from":"{from_version}","to":"{to_version}","at":%s}}\\n' "$1" "$(date +%s)" > "$H/update-result.json"; }}
sleep 1
if [ "{mode}" = "update" ]; then
  rm -rf "$H/app.previous"
  mv "$H/app" "$H/app.previous" && mv "$H/app.new" "$H/app" || {{ result "failed"; exit 1; }}
  restart
  if came_back; then result "updated"; exit 0; fi
  # The new version did not start. Put the old one back.
  rm -rf "$H/app.failed"
  mv "$H/app" "$H/app.failed" && mv "$H/app.previous" "$H/app"
  restart
  came_back; result "went_back"
else
  mv "$H/app" "$H/app.swap" && mv "$H/app.previous" "$H/app" && mv "$H/app.swap" "$H/app.previous" || {{ result "failed"; exit 1; }}
  restart
  if came_back; then result "restored"; else result "failed"; fi
fi
"""
    SCRIPT.write_text(script, encoding="utf-8")
    SCRIPT.chmod(0o700)
    with open(LOG, "a", encoding="utf-8") as log:
        subprocess.Popen(["/bin/bash", str(SCRIPT)], stdout=log, stderr=log, stdin=subprocess.DEVNULL, start_new_session=True)


def _apply() -> None:
    try:
        with _lock:
            available = dict(_available) if _available else None
        if not available:
            raise RuntimeError("Check for updates first.")
        HOME.mkdir(parents=True, exist_ok=True)
        bundle = HOME / "update.tar.gz"
        _set(step="Downloading the new version")
        try:
            _fetch(available["url"], bundle)
        except (requests.RequestException, OSError):
            raise RuntimeError("The download failed. Nothing was changed. Try again.")
        _set(step="Checking the download")
        try:
            _unpack(bundle)
        except (tarfile.TarError, OSError):
            raise RuntimeError("The update file is damaged. Nothing was changed. Try again.")
        finally:
            bundle.unlink(missing_ok=True)
        _set(step="Getting it ready")
        _install_packages()
        _set(step="Restarting StarFerret")
        _hand_over("update", _clean(_version_of(ROOT)), _clean(_version_of(NEW) or available.get("version")))
    except RuntimeError as exc:
        shutil.rmtree(NEW, ignore_errors=True)
        _set(running=False, step="", error=str(exc))
    except Exception:
        shutil.rmtree(NEW, ignore_errors=True)
        _set(running=False, step="", error="The update stopped unexpectedly. Nothing was changed.")


def _guard() -> None:
    if not installed():
        raise RuntimeError("This copy runs from source code, so it is updated with git, not from here.")
    with _lock:
        if _state["running"]:
            raise RuntimeError("An update is already running.")
        _state.update(running=True, step="Starting", error=None)


def start_update() -> None:
    _guard()
    threading.Thread(target=_apply, name="starferret-update", daemon=True).start()


def go_back() -> None:
    if not PREVIOUS.is_dir():
        raise RuntimeError("There is no earlier version to go back to.")
    _guard()
    _set(step="Restarting StarFerret")
    _hand_over("back", _clean(_version_of(ROOT)), _clean(_version_of(PREVIOUS)))
