# supervisor/ notes

Living file. Update it at the end of every task that touches this folder.
Rules for this file are in the root `AGENTS.md`, section 6.

## Status (2026-11-14)

- Serves `control-web/dist` as the Control site on this process (port 7411).
- CORS on `/api/control/*` removed; Control UI is same origin.
- `GET/POST /api/control/board/ollama` forwards Board Ollama settings for the
  Models page. `meta` includes `board_port` for "Open the Board".

## Status (2026-11-12)

- New: `GET /api/control/usage?days=N` (any signed in role). Totals, per day,
  people, folders, models. Built in `usage.py` from the Board's
  `usage_events` table, opened read only.
- New: `/api/control/apps` lists the Board first as a built in app
  (`apps.board_entry()`), so the Apps page shows everything installed.
- Control API works for users, apps (Compose), models, machine, Board lifecycle.
- New: apps with `launchd:` in their manifest are treated as native when the
  installer's plist exists. Only `open-webui` has it.
- Control API works for users, apps, models, machine, Board lifecycle.
- **Apps list is fixed to three:** Board, Open WebUI, n8n (`ALLOWED_APPS` in
  `apps.py`). Board uses LaunchAgent when present, else `process_board`.
- Apps with `launchd:` are native when the installer's plist exists
  (`open-webui`, `board`).
- `GET /api/control/metrics`: GPU, memory, processor now, ten minutes of
  history, and a Metal report built from Ollama's `/api/ps` (`size_vram` over
  `size`). Verified on a test Mac with `deepseek-r1:8b`: 100% on GPU, and the
  Ollama log showed 37 of 37 layers offloaded through Metal.
- `GET /api/control/capacity` and `POST /api/control/capacity/measure`
  (`{"models": "all"}` tests every model, otherwise the default one). The test
  is per model and runs in the background (`capacity.py`): it records what the
  model is (size, quantization, engine), refuses to load one bigger than the
  room left, loads it sized for 1 to 8 conversations and checks each stays
  fully on the GPU and in memory, then sends 1 to 8 questions at once, three
  runs each, averaged. Verified on a test Mac on 2026-11-11:
  `deepseek-r1:8b` (llama.cpp, Q4_K_M) 4 at once, held back by memory;
  `gemma4` (MLX) 8 or more at once; `qwen3.8:27b` (MLX, 16.9 GB) refused, 9.5
  GB of room.
- **Real load is recorded.** The sampler writes every reading into
  `load_minutes` in `control.db` (kept 30 days). `capacity.real_load()`
  averages it: share of time the AI was answering over 24 hours and 7 days,
  the busiest hour, most people on the Board at once, and 24 hourly bars.
  Verified with seeded data on a scratch copy.
- `GET /api/control/people` (admin): Board names from message history, who is
  on the Board now, Open WebUI accounts, Control admins.
- Catalog apps carry `category`, `status`, `note`, `homepage`, `secrets`.
  Compose runs with a generated env file per app.
- Docker state is reported as installed and running separately.

## Known gaps

- Model download state is in memory. A Control restart forgets it (and drops the stream, so Ollama may stop the pull); pulling again resumes.
- The Board can still pull a failover model by itself (`server/ollama_client.py`, `allow_pull`), outside Control and without progress.
- **People no longer includes chat accounts.** Open WebUI reading was removed
  with Open WebUI. LibreChat keeps accounts in MongoDB, which Control cannot
  read without a new dependency. "People using" is Board names only.
- An app with no Compose file and no installer service (LibreChat on a Mac the
  installer has not run on) reports `runtime.installed: false` and cannot be
  started. Seen on a test Mac.

- **Native app path is untested end to end.** Verified only that with no plist
  present, status falls back to the old Compose behavior. Start, stop, and
  health with a real plist have not been exercised.
- `update_app` on a native app just returns an error telling the user to rerun
  the installer. It should upgrade in place.
- The Board is now a LaunchAgent on installed Macs. `process_board.stop()`
  only knows about a pid file it wrote itself, so Control's "stop Board"
  button will not stop a LaunchAgent Board (launchd restarts it anyway).
- **A running copy of Control from before these routes** must be restarted
  to serve `/metrics` and `/people`.
- No Compose app has been started with the new env file path. `start` was
  exercised only up to the "Docker is not open" message.
- Open WebUI account reading was tested against a hand made database with the
  columns the real one is believed to have, not a real install.
- The capacity test has not run with `qwen3.8:27b` or on a 128GB Mac. On a test Mac that model was refused as too big.
- **MLX models: memory per conversation is not measured.** Ollama reports the
  same figure (8.76 GB for `gemma4`) at every conversation size, so the test
  only confirms the model fits and marks the memory limit unknown. Their
  capacity is the speed limit alone.
- The test stops at 8 at once. `gemma4` was still comfortable there, so its
  real limit is higher. Shown as "8+".
- Ollama runs with `OLLAMA_NUM_PARALLEL=1` (read from its log). Questions
  queue. Speeds are what a person feels with queueing, not side by side speed.
- "Other apps" memory is read once, at the start of the test. A Mac that later
  runs more apps has less room than the test says.
- Owner confirmed MLX builds only. Overview marks any other model "Not an MLX
  build". Nothing stops one being pulled or set as default yet.
- "People using" counts Board names and Open WebUI accounts only. People who
  use other apps are not counted.
- Load recording pauses during a capacity test and that stretch is deleted, so
  tests do not show up as real use.
- "Answering" means the GPU read 60% or more (`BUSY_GPU_PERCENT`). A Mac
  that also drives a busy screen could read high without the AI working. It is
  not a count of questions; Ollama does not report those.
- The ten minute live chart lives in memory: ten minutes, lost on restart.
- No requests, tokens, or queue numbers. See `../TODO.md` section 4b.
- `STARFERRET_MODEL` in the env file falls back to `qwen3.8:27b` when
  `OLLAMA_MODEL` is unset, even if that model is not on the Mac.
- No smart routing, no API key storage, no cluster or multi node awareness, no SSO.
- `health._lan_ip()` reads `STARFERRET_HOST`.
- **Usage counts the Board only.** LibreChat, n8n, Open WebUI, and code
  editors talk to Ollama directly, so Control cannot see them. This needs the
  one shared endpoint from `../TODO.md` section 2.
- Usage has no export, no per person limits, and no cost or savings figure.
- No tests.

## Decisions

- 2026-11-15 — Identifiers use the StarFerret names, with no fallback to the previous ones, so the public source does not contain them. An existing install signs in to Control again, Board users retype their display name once, and a Docker app started under the previous prefix is stopped by hand. Env vars are `STARFERRET_HOST` and `STARFERRET_CMD_TIMEOUT`.
- 2026-11-14 — The installer reaches Control with a local key file (mode 600), not a localhost exemption, because a web page open in this Mac's browser also connects from 127.0.0.1. For the same reason, "from this Mac" now also checks `Host` and `Origin`.
- 2026-11-14 — First admin is locked to localhost or a setup token on disk, not to localhost only, so a headless Mac can still be set up from a laptop with the installer's link. Control keeps listening on the network (an owner decision in the one click install plan).
- 2026-11-09 — Native apps are detected by plist presence, not a database
  flag, so Control stays correct if the user installs or uninstalls outside it.
- 2026-11-09 — Native status uses the manifest `health` URL instead of asking
  launchd, because "loaded" does not mean "answering".

- 2026-11-12 — Control reads `data/board.db` directly instead of asking the
  Board over HTTP. The Board has no login, so a Board route would show who
  uses AI to anyone on the network. Cost: Control and Board must share `data/`.
- 2026-11-11 — GPU load comes from `ioreg` (the graphics driver's own
  counters) because `powermetrics` needs sudo and the free install has none.
- 2026-11-11 — "Is it on Metal" is answered from Ollama's `size_vram`, not from
  GPU load, because load is zero whenever nobody is asking a question.
- 2026-11-11 — People are read straight from `board.db` read only rather than
  through a new Board route, so the Board gains no admin surface without login.
- 2026-11-11 — `STARFERRET_DATA_DIR` added to both `paths.py` files so a test
  copy can run beside a running copy without sharing databases.

- 2026-11-11 — Owner: the dashboard is for a non technical person and should
  only say capacity and people, in AI terms. So Overview reads from
  `capacity.py`, and chip, memory, and disk numbers stay off it. Memory and
  GPU problems reach the owner as plain warnings instead of meters.
- 2026-11-11 — Owner rejected a one question speed estimate: capacity must
  be measured against memory and averaged. So the test is a real concurrent
  load test with a memory check. Do not replace it with a formula.
- 2026-11-11 — Memory is checked by loading the model at each size and
  reading Ollama's real allocation and GPU share. The first version took the
  difference between two loads; the same load read 4.44 GB then 4.92 GB, so
  the difference was noise. Do not go back to it.
- 2026-11-11 — A model whose file is bigger than the room left is never
  loaded. Loading it would swap and freeze the Mac for everyone.
- 2026-11-11 — Two numbers in `capacity.py` are still assumptions, not
  measurements, and the owner has not approved them: `COMFORT_SPEED` (10
  tokens per second felt by each person) and `PEOPLE_PER_ANSWER` (10 named
  people per answer slot, a planning estimate). The second
  can only be measured from real usage, which is not recorded yet.

- 2026-11-11 — Overview no longer shows the people total (answers at once
  times 10). The owner asked for people at once only. `seats` is still in the
  API but unused by the UI.

## Next up

1. Test native start, stop, and status against a real install.
2. Make Board lifecycle aware of the LaunchAgent.
3. Native update: `uv tool upgrade` for Open WebUI.
4. API key storage and routing policy for smart routing (`../TODO.md` section 2).

## Log

- 2026-11-15 — Added `extensions.py`: modules named in `STARFERRET_EXTENSIONS` can add routes and sign in buttons (`/meta` returns `sign_in_options`), sign a user in with `start_session`, and send a failed sign in back with `fail_sign_in` (a short lived cookie that `/meta` returns once as `sign_in_error`, so a link cannot put its own words on the sign in screen). Verified with a scratch Control and a demo extension: no buttons without one, button and admin only route with one, cookie sign in works, a missing or failing extension is skipped and logged.
- 2026-11-15 — Compose prefix, Control cookie, and `STARFERRET_HOST` use the StarFerret names. Notes no longer name a specific test machine. Verified by compiling the package and by `GET /api/control/health` on a scratch Control, which reports `starferret-control`.
- 2026-11-14 — Local key (`data/control/local-key`, `X-StarFerret-Local-Key`) for tools on this Mac, and `_request_is_local` now also requires a local `Host` and, when sent, Control's own `Origin`. Closes a hole from earlier the same day where a web page in this Mac's browser could create the first admin, or reset all admins, with a text/plain POST. Verified on scratch 7421: key from this Mac 200, from the LAN, wrong, or missing 401; bootstrap with a foreign Origin (JSON and text/plain) 403, with a rebinding Host 403, reset-admin with a foreign Origin 403, own Origin 200; key file mode 600, kept across admin creation.
- 2026-11-14 — Model pull runs in the background with streamed progress (`models.pull_model`, `list_pulls`, `GET /api/control/models/pulls`). Verified on scratch 7421 against a fake streaming Ollama: start answers 202 in about 2 ms, a second start joins, progress walks 0 to 99 then done, and error line, dropped stream, and unknown name each end as failed with a plain message; 401 without sign in. No real model pulled.
- 2026-11-14 — `/api/control/bootstrap` needs localhost or the setup token (`data/control/setup-token`); `meta` reports `setup_local`. Verified on scratch 7421 from the LAN address: no token 403, wrong token 403, token kept across restart, right token 200 and file deleted, second bootstrap 400; localhost without token 200.
- 2026-11-14 — Control SPA serving, board/ollama routes, CORS removed. Verified
  health + SPA on scratch 7421; Board proxy gone (404 on 7420/api/control).
- 2026-11-12 — Added the usage summary route and the built in Board app entry. Verified through the Board proxy on a second copy (7420 and 7421): summary matched the rows, 401 without sign in, Board listed as running.
- 2026-11-12 — `ALLOWED_APPS` is now board, librechat, n8n. Removed Open WebUI account reading. Verified by listing manifests and by the refusal message for LibreChat.
- 2026-11-12 — Apps allowlist is Board, Open WebUI, n8n. Board start/stop falls
  back to `process_board` when no LaunchAgent. Verified `list_manifests()` returns three.

- 2026-11-11 — Capacity test is per model with model details, a direct memory check, and "test every model". Verified by a full every model run through the route on a scratch copy.
- 2026-11-11 — Added per minute load recording and averaged real load (owner asked to see the real load averaged). Verified with seeded data through `capacity.real_load()` and in the browser.
- 2026-11-11 — Capacity is now a measured load test (memory plus concurrent speed, averaged over three runs). Verified by running the whole test through the route on a scratch copy and reading the result in the browser.
- 2026-11-11 — Added `metrics.py`, `people.py`, catalog fields, per app env files, and Docker running detection. Verified on a scratch copy (ports 7420 and 7421) with curl and in the browser; Metal report verified against a live Ollama.
- 2026-11-09 — Added `launchd:` native app support in `apps.py`. Verified import and the no plist fallback only.
