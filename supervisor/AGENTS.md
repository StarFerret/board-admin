# supervisor/: Control

Read the root [`AGENTS.md`](../AGENTS.md) first, then [`NOTES.md`](NOTES.md).
Behavior is described in [`../DOCS.md`](../DOCS.md).

## Purpose

Control is the admin side of the product: install and run apps, manage models,
manage admin users, show usage (who is using AI and how much), show machine
health. It is the "lightweight manager for a person with three jobs". It runs
as its own process on port **7411** (`python -m supervisor`) and serves the
Control UI from `control-web/dist`. The browser talks to 7411 for Control;
the Board on 7410 no longer proxies admin APIs.

## Files

| File | Owns |
|---|---|
| `app.py` | Flask routes under `/api/control/*`, Control SPA static files, auth decorator `require_auth(*roles)` |
| `apps.py` | App catalog: read manifests, status, start, stop, update |
| `models.py` | Ollama model list, pull, delete, set the Board default |
| `health.py` | Machine snapshot: LAN address, disk, memory, Ollama, Docker |
| `usage.py` | Usage summary, read only from the Board's `usage_events` table |
| `metrics.py` | Live utilization (GPU, memory, processor), history sampler, the Metal report |
| `capacity.py` | Capacity in people, **measured**: a background load test (memory per conversation, then several questions at once, averaged) |
| `people.py` | Who uses this Mac: Board names and Board presence. Read only. LibreChat accounts are not read yet. |
| `process_board.py` | Start, stop, and probe a Board process the supervisor launched |
| `store.py` | SQLite at `data/control.db`: users, sessions, settings, app state |
| `paths.py` | All paths. Add new paths here, never hardcode them elsewhere. |
| `extensions.py` | Optional extensions: modules named in `STARFERRET_EXTENSIONS` add routes and sign in buttons through `ExtensionContext`. None by default. |

## Rules

1. **Privilege lives here, not in the Board.** Docker, `launchctl`, model
   pulls, and anything that changes the machine belong in this package. Never
   expose these to the agent sandbox in `server/`.
2. **Never reimplement an app.** Control installs, starts, stops, updates,
   health checks, and deep links. It does not render chat or workflows.
3. **Every route that changes state needs `@require_auth(...)`** with the
   least role that makes sense. Roles: `admin`, `operator`, `viewer`. Read
   only status can allow `viewer`.
4. **Two ways an app can run, both must keep working:**
   - **Compose:** manifest has `compose:`. Uses `docker compose -p
     starferret-<id>`.
   - **Native:** manifest has `launchd: <label>` and that plist exists in
     `~/Library/LaunchAgents` (the Mac installer put it there). Status is the
     `health` URL; start and stop use `launchctl`. Native wins when present.
   When you add behavior to `status_for`, `start_app`, `stop_app`, or
   `update_app`, handle both paths.
5. **Subprocess calls always have a `timeout`, `check=False`, and
   `capture_output=True`.** Turn failures into a short `RuntimeError` message
   the UI can show. Never let a hung `docker` call hang the request.
6. **Probes must be fast.** `/api/control/machine` and `/apps` are polled by
   the UI. Keep network timeouts at a few seconds.
7. **No new required dependency without asking.** The free install has to
   stay small. Check `server/requirements.txt` (shared by both processes).
8. **Do not print or return secrets.** When API keys arrive (smart routing),
   store them encrypted in `store.py` and return only a masked form.
9. The Compose project prefix is `starferret-`. A container started
   under an older prefix is not picked up. Stop it by hand in Docker.

10. **Extensions are optional.** Control must work the same with none
    loaded. Keep `ExtensionContext` small and backward compatible: forks and
    add ons depend on it. Never check for an extension to unlock or hide a
    feature that lives in this repo.
11. **Metrics use only what ships with macOS** (`ps`, `vm_stat`, `sysctl`,
    `ioreg`, `system_profiler`). No sudo, no `powermetrics`, no `psutil`.
12. **Read other apps' databases read only** (`mode=ro`), as `people.py` does.
    Control never writes to `board.db` or another app's database.
13. **Compose apps get secrets from `_env_file`** (`data/stack/env/<id>.env`),
    listed under `secrets:` in the manifest. Never put a secret in a Compose
    file and never return one from a route.
14. **"Docker installed" is not "Docker running".** Use `docker_running()` and
    `docker_state()["message"]` for anything the user sees.

## Testing without touching a running copy

```bash
STARFERRET_DATA_DIR=/some/scratch/dir PORT=7420 CONTROL_PORT=7421 \
  .venv/bin/python -m supervisor &
STARFERRET_DATA_DIR=/some/scratch/dir PORT=7420 CONTROL_PORT=7421 \
  .venv/bin/python -m server
```

Then open `http://127.0.0.1:7421/` for Control and `http://127.0.0.1:7420/` for
the Board. Stop both when done.

## Adding a catalog app

See [`../catalog/AGENTS.md`](../catalog/AGENTS.md). Usually no Python change
is needed: a manifest plus a Compose file is enough.

## Verify

```bash
.venv/bin/python -c "import supervisor.apps as a; print([ (m['id'], m['runtime']['running']) for m in a.list_manifests() ])"
.venv/bin/python -m supervisor            # only if port 7411 is free; ask before stopping a running copy
curl -s http://127.0.0.1:7411/api/control/health
```

Exercise the route you changed with `curl` against Control
(`http://127.0.0.1:7411/api/control/...`) as the UI would. Then update `NOTES.md`.
