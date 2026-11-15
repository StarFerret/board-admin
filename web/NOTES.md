# web/ notes

Living file. Update it at the end of every task that touches this folder.
Rules for this file are in the root `AGENTS.md`, section 6.

## Status (2026-11-14)

- Board UI only. Control pages moved to `control-web/`.
- Header is StarFerret + Settings. No Board | Control switch.
- Links to Control use `getControlUrl()` (hostname + `control_port` from
  `/api/settings/host`). Quiet "Manage this Mac" link at the bottom of Settings.
- Old `/control/...` bookmarks redirect from the Board server to `:7411`.

## Known gaps

- First-run welcome after NameGate still missing (LAN address, open chat/Control).
- No tests.
- Found in a new user walkthrough on 2026-11-14, not fixed: clicking a file in a
  folder does nothing (no preview or download), no drag and drop upload, the
  empty chat gives no example jobs, and "Steer", "Interrupt", "How hard / tries",
  "Context" are jargon for a non technical user.

## Decisions

- 2026-11-15 — Identifiers use the StarFerret names, with no fallback to the previous ones, so the public source does not contain them. An existing install signs in to Control again, Board users retype their display name once, and a Docker app started under the previous prefix is stopped by hand. Env vars are `STARFERRET_HOST` and `STARFERRET_CMD_TIMEOUT`.
- 2026-11-14 — Control leaves this package; Board keeps the `web/` name so
  installer and updater paths stay stable (from the Control split plan, 2026-11-14).
- 2026-11-09 — Product UI keeps its own design, separate from the marketing
  site, until the owner asks for a redesign.

## Log

- 2026-11-15 — Board title, name screen, display-name storage, and the model event use the StarFerret names. People retype their display name once. Verified with `npm run build` and a scratch Board on port 7420: the name screen says StarFerret, joining stores `starferret_name`, and a reload skips the screen.
- 2026-11-14 — Agent page: Stop button while the agent works (calls
  `/api/agents/<id>/stop`), "Stopping…" state. Verified on a test Board (port
  7420, scratch data): Stop mid job left the agent idle within 6 s with "Stopped."

- 2026-11-14 — Control split: removed Control routes and proxy clients; added
  Control URL helper and Settings link. Verified: `npm run build`;
  `grep -rn control web/src` only helper and links. Not clicked: full Board
  folder/agent chat path in a browser this session.
