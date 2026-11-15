# catalog/ and stacks/: the apps Control can run

Read the root [`AGENTS.md`](../AGENTS.md) first, then [`NOTES.md`](NOTES.md).
This file covers both `catalog/` (manifests) and `stacks/` (Compose files).

## Purpose

StarFerret does not rebuild AI apps. It preloads a **fixed set of three**:
**Board**, **LibreChat**, and **n8n**, and nothing else (owner, 2026-11-12). Control (`supervisor/apps.py`) reads
manifests on every refresh and only serves ids in `ALLOWED_APPS`. Do not add
catalog entries without an owner decision. Docker apps also need a Compose
file in `../stacks/`.

## Manifest fields (`catalog/<id>.yaml`)

| Field | Required | Meaning |
|---|---|---|
| `id` | yes | Lowercase, stable forever. Used in Compose project names and the database. |
| `name` | yes | Display name, spelled the way the project spells it. |
| `description` | yes | One plain sentence: what a non technical person gets from it. |
| `compose` | for Docker apps | Path to the Compose file, like `stacks/n8n.yml`. |
| `ports` | yes | First port is the one the "Open" link uses. |
| `depends` | no | Other ids or `ollama`. |
| `health` | yes | URL that answers when the app is really up. |
| `deep_link` | no | Whether Control links out to it. Default true. |
| `category` | yes | One of the names in `CATEGORIES` in `supervisor/apps.py`. Groups the Apps page. |
| `status` | yes | `ready` (started from Control and answered from a local model), `beta` (written, not verified; shows "Not yet verified"), `planned` (shows "Coming soon", cannot start, no Compose file). |
| `note` | no | One plain sentence shown under the description. Required for `beta` and `planned`. |
| `homepage` | no | The project's own site. |
| `secrets` | no | `NAME: bytes`. Control generates each once into `data/stack/env/<id>.env` and Compose reads it as `${NAME}`. |
| `launchd` | no | LaunchAgent label when the Mac installer runs it natively, like `com.starferret.openwebui`. When that plist exists, Control uses `launchctl` and ignores `compose`. |

## Rules

1. **Only real, maintained, open source apps** that a company of this size
   would actually use. Check the license allows commercial self hosting.
2. **Pin nothing you cannot explain, but do not use a tag that breaks
   weekly.** State the image tag choice in `NOTES.md`.
3. **Data must survive an update.** Every Compose file uses a named volume for
   app data. Never bind mount into the repo.
4. **Point apps at the local model runtime.** From a container, Ollama on the
   Mac is `http://host.docker.internal:11434`. Native apps use
   `http://127.0.0.1:11434`.
5. **One port per app, no clashes.** Taken: 7410 Board, 7411 Control, 8080
   Open WebUI, 5678 n8n, 11434 Ollama. List new ones in `NOTES.md`.
6. **No app may need a cloud account or a paid key to start.**
7. **`restart: unless-stopped`** on every service.
8. **Prefer a native install path for anything in the free tier**, because the
   free install has no Docker. That means work in `installer/macos/install-starferret.sh`
   plus a `launchd:` field here.
9. **Anything that runs a model itself must be native, never Compose.**
   Containers on a Mac cannot reach the GPU (Metal), so image generation,
   speech, and embedding servers would crawl. Apps that only call Ollama are
   fine in Compose because Ollama runs on the Mac itself.
10. **Compose files may use `${STARFERRET_HOST}` (this Mac's network address)
    and `${STARFERRET_MODEL}` (the default model)**, plus the app's own
    `secrets`. Put config files inline with a top level `configs:` `content:`
    block, not a bind mount.
11. **New apps start as `beta`.** Only set `ready` after the step by step below.
12. When an app really ships, tick it in `../TODO.md` section 4. The marketing
   site is kept elsewhere; say in your report that its copy may need updating.

## Adding an app, step by step

1. Write `stacks/<id>.yml`. Start it by hand: `docker compose -f stacks/<id>.yml up -d`.
2. Open it in a browser. Confirm it can reach Ollama and list a model.
3. Write `catalog/<id>.yaml` with a `health` URL you have curled.
4. Check Control sees it:
   `.venv/bin/python -c "import supervisor.apps as a; print(a.get_manifest('<id>'))"`
5. Start and stop it from Control → Apps.
6. Update `NOTES.md`, `../TODO.md`, and `../DOCS.md` if behavior changed.

Do not list an app as done on the strength of a YAML file. It is done when it
starts from Control and talks to a local model.
