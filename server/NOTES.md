# server/ notes

Living file. Update it at the end of every task that touches this folder.
Rules for this file are in the root `AGENTS.md`, section 6.

## Status (2026-11-14)

- **Office jobs finish now.** "Read this .docx and write me a Word doc" ran end
  to end in 36 s on gemma4 and produced a real .docx with headings and bullets.
  Before: 30+ minutes with no result.
- New folders start with the `office` and `documents` packs on.
- `office_create` makes a new .docx or .xlsx. `write_file` refuses Office extensions.
- Stop: `POST /api/agents/<id>/stop`; cancels mid stream.
- Failover falls back only to MLX models, and says so in the agent chat.

- No longer proxies `/api/control/*`. Old `/control` and `/control/<path>`
  redirect to the Control port. `/api/settings/host` includes `control_port`.

## Status (2026-11-12)

- **Usage is recorded.** Every turn writes one row to `usage_events` in
  `data/board.db`: person (display name), agent, folder, model, model calls,
  tokens in and out, duration, outcome. See `usage.py`. The Board has no route
  for it; Control reads the table read only.
- Not changed in the StarFerret work so far. Everything in `../DOCS.md` is the
  last known description: folders, agents, send, steer, interrupt, tool packs,
  external MCP, schedules, failover.
- On installed Macs it now runs as LaunchAgent `com.starferret.board`
  (`python -m server`) with `OLLAMA_MODEL` set by the installer.

## Known gaps

- The Board still pulls a ladder model by itself when Ollama has some models but none on the ladder work (`allow_pull`). That is a machine change outside Control, against rule 2.
- **No smart routing.** All chat goes to Ollama. Marked coming soon on the site.
- No awareness of other Macs. One Board talks to one Ollama.
- Token counts and timings from Ollama are not recorded, so Control cannot
  show usage per person. See `../TODO.md` section 4b.
- The ladder's last rung, `gemma4:12b-mlx`, has not been pulled on a real Mac
  yet. Its MLX runner is taken from Ollama's library listing.
- Failover persists the new model for good. A qwen3.8:27b that cannot load
  because memory is busy (the model asks for more memory than is free)
  moves the whole Board to gemma4 until someone changes it back.
- Failover may `ollama pull` a missing ladder model on its own (gigabytes,
  no prompt).
- The goal loop is built for jobs. A plain question still goes through goal
  extract and the done check, which costs two extra model calls.
- `office_create` does not make .pptx.
- No login. Anyone on the network with the address can use it. Fine for the
  free tier; the paid tier promises SSO.
- `__main__.py` error text mentions Task Manager and `python.exe`; it was
  written on Windows.
- `sandbox.py` has a `docker_available()` helper. Check whether anything in
  the Board still depends on Docker before adding to it.
- Usage gaps: a steer is counted under whoever started the turn. Model calls
  outside a turn (agent identity on create) are not counted. Scheduled turns
  show as the person "Schedule". Names are typed, not verified.
- No tests.
- The state of this package was read, not exercised, on 2026-11-09. Treat
  anything not listed in the Log as unverified by the current docs.

## Decisions

- 2026-11-15 — Identifiers use the StarFerret names, with no fallback to the previous ones, so the public source does not contain them. An existing install signs in to Control again, Board users retype their display name once, and a Docker app started under the previous prefix is stopped by hand. Env vars are `STARFERRET_HOST` and `STARFERRET_CMD_TIMEOUT`.
- 2026-11-14 — The Board is "here are my files, go do this", not a chat app, so
  the goal loop stays and was fixed instead of adding a plain answer path
  (owner, this session).
- 2026-11-14 — `web` stays off in new folders: it sends queries off the Mac.
  `office` and `documents` are on because files are the point of a folder.
- 2026-11-14 — MLX models that reject `format: json` get the same prompt without
  it and the harness parses JSON from text, instead of dropping JSON checks.

- 2026-11-09 — Board stays as is while the installer and Control catch up.

- 2026-11-12 — Usage is one row per turn, not per model call. An admin thinks
  in messages; per call rows would be about ten times the data for no visible gain.
- 2026-11-12 — The running tally is thread local (`usage.begin/note/finish`),
  fed from `ollama_client.chat` and `chat_stream`, so the harness functions
  did not need new arguments and smart routing can feed the same `note()`.

## Next up

1. Smart routing (`../TODO.md` section 2): one chat entry point that can send
   to Ollama or a frontier API using the customer's key.
2. Rename user facing strings as part of the single rename change.
3. Per workspace switch to forbid cloud routing.

## Log

- 2026-11-15 — User-Agent, MCP client name, and `STARFERRET_HOST` / `STARFERRET_CMD_TIMEOUT` use the StarFerret names. Verified by compiling the package.
- 2026-11-15 — Ladder's last rung is now `gemma4:12b-mlx` (was GGUF `deepseek-r1:8b`). Ladder matching now prefers exact tags, since two rungs share the `gemma4` family; before, a Mac with only `gemma4:latest` would never fetch the smaller one. Verified with a script over `failover_model_chain` and `next_pull_candidate` for seven installed sets. Not run against a live Ollama.
- 2026-11-14 — Fixed Office jobs never finishing. Cause: Ollama's MLX runner
  returns 501 for `format: json`, so every done check failed and the 501 also
  triggered failover down to the GGUF model. Added the no-JSON retry, MLX only
  fallbacks with a chat notice, `office_create`, the `write_file` Office guard,
  default `office`/`documents` packs, and Stop. Verified on a test Board (port
  7420, scratch data, real Ollama, gemma4 after qwen could not load): docx
  review job done in 36 s, output opens as a Word file; Stop within 6 s; xlsx
  create, jail escape, and the write_file guard checked by script. Not tested:
  qwen3.8:27b itself (does not fit in memory on this Mac), .pptx, schedules.
- 2026-11-14 — When Ollama answers but has no models, `_run_with_failover` raises `ModelNotReady` with a plain "still downloading, see Control → Models" message (shown without the "Harness error:" prefix) and does not pull a ladder model itself. Verified by calling it against an empty fake Ollama with `pull_model` stubbed: message raised, no pull; Ollama down still takes the old path. Not tested: a real chat on a fresh install.
- 2026-11-14 — Removed Control proxy; added `/control` redirect and `control_port`
  on host settings. Verified curl redirect and 404 on `/api/control/health`.
- 2026-11-12 — Added usage recording (`usage.py`, table in `db.py`, token counts kept from the stream in `ollama_client.py`, begin and finish in `harness._run_turn`). Verified on a second copy (port 7420, empty data folder) against a stand-in model server: four turns from three names wrote four rows with tokens. Not run against real Ollama.
- 2026-11-11 — Added `GET /api/presence` (names with the Board open now) for Control → People, and `STARFERRET_DATA_DIR` in `paths.py`. Verified on a scratch Board: the route answers; it returned an empty list because no one had a Board page open.
- 2026-11-09 — No code changes. Notes file created from a read of the package.
