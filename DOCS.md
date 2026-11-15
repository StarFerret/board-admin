# StarFerret — features and implementation

This document describes what the product does and how the important pieces work in code. For install and run steps, see [README.md](README.md).

## Mental model

```
StarFerret (one product)
├── Board — folders, agents, chat/steer, files (trust-the-LAN collaborators)
└── Control — apps, models, users, machine (admin; separate supervisor process)
```

```
Board (folders)
  └── Folder / workspace
        ├── One machine directory (jail)
        ├── Rules (rules/*.md) — always injected
        ├── Skills (skills/*/SKILL.md) — listed; agent reads on demand
        ├── Tool packs (web / office / documents) — optional
        └── Agents (each has a chat URL /a/<id>)
```

Agents in the same folder share the same files. They never see paths outside that folder’s root.

---

## Board + Control boundary

Two sites, two processes, two UI folders:

| Process | Port | Owns |
|---------|------|------|
| Board (`python -m server`) | `7410` | Agents, workspaces, Socket.IO, Board SPA (`web/dist`) |
| Supervisor (`python -m supervisor`) | `7411` | Admin auth, Control SPA (`control-web/dist`), Compose catalog, model pull/delete, Board lifecycle, health |

**Do not** put Docker socket access or installer privileges inside the agent harness / sandbox. Control never reimplements LibreChat or n8n — it installs, starts/stops, and deep-links.

- Board: `http://<mac>:7410/` — folders and agents. Display name gate only.
- Control: `http://<mac>:7411/` — Overview, Usage, Apps, Models, People, Machine, Updates. Local admin sign in.
- Model downloads: `POST /api/control/models/pull` starts a background download and returns 202 at once; `GET /api/control/models/pulls` gives each download's state (`running`, `done`, `failed`), bytes, and percent. Kept in memory only; pulling the same name again after a Control restart resumes, because Ollama keeps the parts it has.
- Local key: `data/control/local-key` (mode 600) lets tools on this Mac, such as the installer, call Control with the `X-StarFerret-Local-Key` header and no admin password. It only works from this Mac. Reading the file already needs this Mac's user, so it grants nothing new.
- "From this Mac" (first admin, admin reset, local key) means: connected from 127.0.0.1 or ::1, `Host` is a local name (stops DNS rebinding), and a browser `Origin`, if sent, is Control itself (stops other web sites open in this Mac's browser).
- First admin: only from the Mac itself (localhost), or from another machine with the one time setup link `http://<mac>:7411/?setup=<token>`. The token lives in `data/control/setup-token` (mode 600) until the first admin exists, then it is deleted.
- Board Settings has a quiet "Manage this Mac" link to Control. Old `/control` bookmarks on 7410 redirect to 7411.
- Roles: `admin` | `operator` | `viewer`
- App manifests: [`catalog/`](catalog/) → Compose files in [`stacks/`](stacks/). The list and what is verified: [`catalog/NOTES.md`](catalog/NOTES.md)
- Mac LaunchAgent scaffolding: [`installer/macos/`](installer/macos/)
- Windows installer: **deferred** until the Mac path is stable

Ollama host/model management lives under **Control → Models**. Board **Settings** keeps board name, LAN share, and MCP JSON only.

---

## Features

### Board and folders (Drive-style)

- Home lists folders like a file browser. The label defaults to **Workspaces** and can be renamed in Settings. Hover **N here** to see who is looking. **Copy link** copies the board URL for the whole app.
- Inside a folder, agents and files share one explorer list (Name / Type / Status). Click an agent to chat; click a directory to go in.
- Toolbar: New agent, New folder, Upload. Breadcrumbs: Workspaces / Folder / path.
- Each folder’s machine root defaults to `data/workspaces/<id>/` (optional `drive_path` still exists in the API for power users; it is not shown in the end-user UI).

### Agents

- An agent is a named chat persona with emoji/color identity (minted via Ollama when created).
- Create from the folder page; creation navigates to `/a/<agent-id>`.
- Agents can be moved between folders, archived, restored, or deleted.
- Each agent has a shareable URL. Visitors enter a display name; presence shows who is looking.

### Chat modes

| Mode | Behavior |
|------|----------|
| **Send** | Starts (or replaces) a turn: extract a goal, then tool loop until done or effort exhausted. |
| **Steer** | If a turn is already running, queues mid-run guidance. Injected into the model as an operator correction without killing the turn. If nothing is running, treated like Send. |
| **Interrupt** | Cancels the current turn, then starts a new one with the new message. Needs a typed message. |
| **Stop** | Shown while the agent works. `POST /api/agents/<id>/stop` cancels the turn, mid stream too, without starting a new one. The chat shows "Stopped." |

Effort is a per-agent budget of model/tool steps. The harness nudges the model to keep going and call `mark_goal_done` only when finished.

### Rules, skills, and outputs (files on disk)

Browse the folder in the UI (or open the host path in Finder). There are no invent-in-browser forms for rules/skills — put files on disk yourself.

- **`rules/`** — Drop `.md` / `.txt` files here. Every agent in the folder gets their content in the system prompt (always on).
- **`skills/`** — Folders with a `SKILL.md`. The system prompt lists names + descriptions; the agent is told to `read_file` the skill path when it fits.
- **`outputs/`** — Seeded empty. The system prompt tells agents to save every new deliverable here (`outputs/<clear-name>.ext`) so operators can find finished work in one place.
- Rules/skills are discovered from the jail at read time (`sandbox.discover_rules` / `discover_skills`).

### Built-in tool packs (“MCP” packs)

These are **in-process tools**, not external MCP servers. Enable them per folder under **Tools**.
New folders start with `office` and `documents` on (`store.DEFAULT_FOLDER_TOOLS`); `web` stays off because it sends queries off the Mac.

| Pack id | Tools | What it does |
|---------|--------|----------------|
| `web` | `web_search`, `web_fetch` | Search the public web; fetch a public page as text |
| `office` | `office_read`, `office_create`, `office_replace`, `office_add_paragraph`, `office_set_cell` | Read `.docx` / `.xlsx` / `.pptx`; create a new `.docx` / `.xlsx` from text; edit existing ones. `write_file` refuses Office extensions so it cannot write a broken file. |
| `documents` | `documents_read`, `documents_edit` | Read/edit text files in the jail (office files redirect to office tools) |

Plus always-on sandbox tools from the harness: `list_files`, `read_file`, `write_file`, `run_command`, `mark_goal_done`.

### Settings, Control, and LAN

- **Settings** (`/settings`) holds board name, LAN share origin, and MCP servers.
- **Control** (`http://<mac>:7411/`) holds apps (Compose catalog), models (Ollama), users/roles, and machine health.
- Board binds **`0.0.0.0:7410`** by default; supervisor binds **`0.0.0.0:7411`**.
- Model picker and failover ladder live with Ollama (Control → Models / Board status).

### Usage

- The Board writes one row per turn to `usage_events` in `data/board.db` (`server/usage.py`): display name, agent, folder, model, model calls, tokens in and out, duration, outcome.
- Control reads that table read only and serves `GET /api/control/usage?days=N` (`supervisor/usage.py`). The UI is **Control → Usage**.
- Only Board turns are counted. Other apps reach the model runtime directly.

### Live updates

Flask-SocketIO rooms:

- `board` — folder/agent roster, status, presence
- `workspace:<id>` — folder file events
- `agent:<id>` — messages, tokens, goal progress, steers, errors

---

## How web search works

Web capability is the **`web` tool pack** in `server/mcp_builtin.py`. No API key. No third-party search SDK.

### Enable

1. Open a folder.
2. Under **Tools**, add **Web search**.
3. That pack id is stored on the workspace (`tools` list).
4. On the next agent turn, `_folder_tools` in `harness.py` merges `mcp_builtin.tools_for(packs)` into the Ollama tool schema, and the system prompt gets a short blurb that those tools exist.

### `web_search`

```
Agent tool call → harness._dispatch_tool → mcp_builtin.call_tool
  → _web_search(query, limit)
```

Implementation:

1. `GET https://www.bing.com/search` with query params `q`, `format=rss`, and `count` (clamped 1–8).
2. User-Agent: `StarFerret/1.0`.
3. Parse the RSS XML (`channel/item`).
4. Return JSON: `{ query, results: [{ title, url, snippet }, ...] }`.

So search is **Bing’s public RSS search endpoint**, scraped via HTTP + XML — not Bing Web Search API, not DuckDuckGo Instant Answer, not a paid key.

### `web_fetch`

```
Agent tool call → _web_fetch(url)
```

Implementation:

1. Only `http` / `https`.
2. Resolve the host; **reject** localhost, `.local`, `.internal`, and any non-global IP (SSRF guard via `ipaddress` + `getaddrinfo`).
3. Follow up to 5 redirects manually, re-checking each host (so a redirect cannot bounce into a private address).
4. Stream at most ~500 KB of body.
5. If HTML, strip tags with a small `HTMLParser` (skip `script` / `style` / `noscript`), collapse whitespace.
6. Return JSON: `{ url, status, text }` with text capped at 12 000 characters.

Typical agent pattern: `web_search` → pick a URL → `web_fetch` → reason / write into the workspace.

### Limits and caveats

- Depends on Bing continuing to serve RSS for that endpoint; HTML layout changes do not break search (RSS does).
- No ranking control beyond Bing’s results.
- Fetch is best-effort readable text, not a full browser (no JS rendering).
- Private/LAN URLs are intentionally blocked.

---

## How the agent loop works

Entry: `POST /api/agents/<id>/messages` with `mode` of `send` | `steer` | `interrupt` → `harness.run_turn`.

1. **Goal extract** — Small Ollama call turns the user message into a concrete goal string.
2. **System prompt** — Name, shared-folder rules, tool blurbs, file index, `rules/` bodies, skill catalog, optional custom prompt/notes, effort budget.
3. **Tool loop** — Chat with tools until `mark_goal_done`, cancel, or effort spent. Steers drained between steps and injected as operator messages.
4. **Failover** — If the active model fails (OOM, timeouts, certain HTTP statuses), `ollama_client` walks the ladder, may `ollama pull` a missing rung, persists the new model, and notifies the UI over Socket.IO. The agent chat gets a plain "Switched to …" line. Fallbacks are MLX only: installed models whose runner is not `mlx`, and anything in `NOT_MLX`, are skipped and never pulled. The model the owner chose always gets its own try. If Ollama answers but has **no models at all** (right after install, while Control downloads the first one), it raises `ModelNotReady` with a plain message pointing at Control → Models and pulls nothing.
5. **JSON calls** — Goal extract and the done check ask for JSON. Ollama's MLX runner answers `format: json` with 501 "structured output is unavailable", so `ollama_client` retries those models without the flag and `harness._parse_json` reads the object out of the plain reply.

Default ladder (largest → smallest):

1. `qwen3.8:27b`
2. `gemma4:latest`
3. `gemma4:12b-mlx`

---

## Architecture map

| Area | Where |
|------|--------|
| HTTP + Socket.IO | `server/app.py` |
| Agent turns, tools, steer/interrupt | `server/harness.py` |
| Ollama probe, chat, pull, failover | `server/ollama_client.py` |
| Folder jail, browse, rules/skills discovery | `server/sandbox.py` |
| Built-in tool packs (web/office/documents) | `server/mcp_builtin.py` |
| SQLite agents/workspaces/messages/settings | `server/store.py`, `server/db.py` |
| Agent mint (emoji/color/tagline) | `server/identity.py` |
| React UI | `web/src/` — Board, Workspace, Agent, Settings, Control pages; `api.js`; `controlApi.js`; Socket hooks |
| Control supervisor | `supervisor/` — auth, apps catalog, models, health, Board process helper |
| App catalog + Compose | `catalog/*.yaml`, `stacks/*.yml` |
| Mac installer scaffold | `installer/macos/install-starferret.sh` + LaunchAgent plist |

Data defaults under `data/` (SQLite board + control DBs, workspace trees, `data/stack/` for supervisor runtime) unless a folder’s `drive_path` points elsewhere.

### Expanding the app catalog

Add a YAML manifest under `catalog/` and a Compose file under `stacks/`. Example fields: `id`, `name`, `description`, `compose`, `ports`, `depends`, `health`, `deep_link`. Control → Apps picks them up on refresh. Future candidates (Whisper, ComfyUI, etc.) follow the same pattern. Windows packaging stays Phase 4.

---

## External MCP (board-wide JSON)

MCP servers live as JSON files under `data/mcp/servers/<id>.json`. Add them in **Settings** by pasting Cursor-style JSON:

```json
{
  "mcpServers": {
    "my-server": {
      "url": "https://mcp.example.com/sse",
      "headers": { "Authorization": "Bearer …" }
    }
  }
}
```

or stdio `{ "command": "npx", "args": ["-y", "…"], "env": {} }`.

Assign each server to **all folders** (`workspaces: ["*"]`) or specific folder ids. Agents in those folders get tools named `mcp__<server>__<tool>`. Runtime: `server/mcp_registry.py` + `server/mcp_runtime.py`. Built-in packs in `mcp_builtin.py` are still separate.

## Sharing a folder

- URL: `{LAN origin}/w/<workspace-id>`
- UI: **Copy link** on Workspaces copies the whole board. Share on a folder (button, hover, or right-click) copies that folder’s `/w/…` link. Hover **N here** to see names.

---

## Related notes

- Frontend component notes: [web/SHADCN_SETUP.md](web/SHADCN_SETUP.md)
