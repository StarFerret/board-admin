# catalog/ and stacks/ notes

Living file. Update it at the end of every task that touches these folders.
Rules for this file are in the root `AGENTS.md`, section 6.

## Status (2026-11-12)

Three manifests. The catalog is closed: do not add a fourth.

| App | Category | How it runs | Port |
|---|---|---|---|
| Board | Core | LaunchAgent `com.starferret.board`, or a plain process in a checkout | 7410 |
| LibreChat | Chat | LaunchAgent `com.starferret.librechat` set up by the installer. No Compose file. | 3080 |
| n8n | Automation | LaunchAgent `com.starferret.n8n` set up by the installer. `stacks/n8n.yml` remains as a Docker fallback. | 5678 |

Open WebUI and its Compose file were removed on 2026-11-12.

## Known gaps

- **LibreChat and n8n have never been started through the new installer
  steps.** Dry run only. See `../installer/NOTES.md`.
- On a Mac where the installer has not run, LibreChat shows as not set up and
  cannot be started from Control. n8n can still start through Docker.
- `stacks/n8n.yml` uses the floating `latest` tag.

## Decisions

- 2026-11-12 — Owner: only Board, Open WebUI, and n8n. Install, run, and
  monitor from Control. No wider catalog until asked.
- 2026-11-09 — Native apps use a `launchd:` field on the same manifest.

- 2026-11-12 — Owner: three apps only. LibreChat replaces Open WebUI. LibreChat
  has no Compose file because the free install has no Docker and one path is
  enough to keep working.

## Next up

1. Run the installer for real and confirm LibreChat and n8n start, stop, and report health from Control.
2. Decide whether to keep the Docker fallback for n8n.

## Log

- 2026-11-12 — Added `librechat.yaml`, made n8n native first, removed Open WebUI. Verified that Control lists the three and refuses to start LibreChat with a plain message when it is not set up.
- 2026-11-12 — Cut catalog to Board, Open WebUI, n8n. Added `catalog/board.yaml`.
  Enforced allowlist in `supervisor/apps.py`. Verified list loads three ids.
- 2026-11-11 — (superseded) Wide beta catalog. Removed 2026-11-12.
