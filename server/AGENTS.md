# server/: the Board

Read the root [`AGENTS.md`](../AGENTS.md) first, then [`NOTES.md`](NOTES.md).
How it works is in [`../DOCS.md`](../DOCS.md). Read the agent loop and folder
jail sections there before changing `harness.py` or `sandbox.py`.

## Purpose

The Board is "a shared drive with agents living in it". People make a folder
(workspace), drop files in, and agents read, write, and run things there, with
several people present at once. It runs on port **7410**
(`python -m server`) and serves the Board UI from `web/dist`. Control is a
separate site on 7411. Old `/control` bookmarks redirect there.

Keep the Board working and simple. Do not grow it at the expense of the
installer, Control, and clustering.

## Files

| File | Owns |
|---|---|
| `app.py` | All HTTP routes, Socket.IO events, Board static serving, Control bookmark redirect |
| `harness.py` | One agent turn: goal extract, system prompt, tool loop, steer, interrupt |
| `ollama_client.py` | Ollama chat, streaming, pull, and the **failover ladder** |
| `sandbox.py` | The folder jail, file browse, rules and skills discovery, `run_command` |
| `mcp_builtin.py` | Built in tool packs: `web`, `office`, `documents` |
| `mcp_registry.py`, `mcp_runtime.py` | External MCP servers from `data/mcp/servers/*.json` |
| `store.py`, `db.py` | SQLite at `data/board.db` |
| `identity.py` | Agent emoji, color, tagline |
| `scheduler.py` | Scheduled agent turns |
| `usage.py` | Usage log: one row per turn in `usage_events` (who, agent, model, tokens) |
| `paths.py` | All paths |

## Rules

1. **The jail is sacred.** Every file path from a user or a model goes through
   `sandbox.jail()` or `sandbox.workspace_jail()`. Never build a path with
   string joins. Never let an agent read or write outside its folder root.
2. **No machine privileges here.** No Docker, no `launchctl`, no installing
   software. That is Control's job. The Board proxies to it.
3. **`web_fetch` keeps its SSRF guard.** It must keep rejecting localhost,
   private, and link local addresses, and recheck after every redirect.
4. **The Board trusts the LAN.** It has no login, only a display name. So
   never add a Board route that changes the machine, exposes secrets, or
   reaches outside workspace folders. Put those behind Control's auth.
5. **Model failures should degrade, not error.** Follow the pattern in
   `ollama_client._run_with_failover`: walk `FAILOVER_LADDER`, persist the new
   choice, tell the UI. The installer picks models from this same ladder; if
   you change the ladder, update `installer/macos/install-starferret.sh` step 1.
6. **Long work never blocks a request.** Turns run in background threads and
   report over Socket.IO rooms (`board`, `workspace:<id>`, `agent:<id>`).
   Emit an event for anything the UI needs to see change.
7. **Tools return strings the model can read**, including on failure. Say what
   went wrong and what to try. Never raise out of a tool call.
8. **Database changes need a migration path.** Customers have live
   `data/board.db` files. Add columns with defaults; never drop or rename
   without a migration in `db.py`.
9. Smart routing will live in or beside `ollama_client.py`. Keep provider
   logic behind one function so the harness does not care where a reply came from.

## Verify

```bash
.venv/bin/python -c "import server.app"                    # imports cleanly
curl -s http://127.0.0.1:7410/api/settings/host            # if a copy is running
```

To test a change live you need the Board running. **Port 7410 is usually in
use by a running copy. Ask before stopping it**, or run a second copy with
`PORT=7420 .venv/bin/python -m server` (it shares `data/`, so do not run
destructive tests).

For harness or tool changes, send a real message to a test agent and read the
result. An import passing proves nothing about a tool loop.

Then update `NOTES.md`.
