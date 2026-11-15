# control-web/ notes

Living file. Update it at the end of every task that touches this folder.
Rules for this file are in the root `AGENTS.md`, section 6.

## Status (2026-11-14)

- Own Vite app for Control. Served by supervisor on port 7411.
- Routes without `/control` prefix. Own shell; "Open the Board" link uses
  `board_port` from `/api/control/meta`.
- Models page talks to Board Ollama only through `/api/control/board/ollama`.
- Apps Start/Stop signature bug fixed (was calling with undefined `id`).

## Known gaps

- Plain wording pass on Machine, Models, Users still needed (carried from web/).
- Start/Stop/Update not clicked against a real native install in this change.
- Sign in is per address; after the split admins sign in once at `:7411`.

## Decisions

- 2026-11-15 — Identifiers use the StarFerret names, with no fallback to the previous ones, so the public source does not contain them. An existing install signs in to Control again, Board users retype their display name once, and a Docker app started under the previous prefix is stopped by hand. Env vars are `STARFERRET_HOST` and `STARFERRET_CMD_TIMEOUT`.
- 2026-11-14 — Shared UI code copied from `web/`, not a workspace package
  (from the Control split plan, 2026-11-14).
- 2026-11-14 — Control is its own site on 7411, not a path on the Board.

## Log

- 2026-11-15 — Sign in screen shows `meta.sign_in_options` as buttons, and shows `meta.sign_in_error` once after a sign in that left Control fails. Verified: build, and screenshots at 1280 and 390 against a scratch Control.
- 2026-11-15 — Control's saved sign-in token and the model event use the StarFerret names. Admins sign in again. Verified with `npm run build` and a scratch Control on port 7421: creating an admin set the `starferret_control` cookie and `starferret_control_token`, then Overview loaded.
- 2026-11-14 — Models page shows each download with a progress bar, plain step words, and bytes; polls every 1.5 s while one runs and every 10 s otherwise, and refreshes the list when one finishes. Verified in the browser against a fake Ollama, at desktop width and 390px (no sideways scroll), across a reload mid download.
- 2026-11-14 — Create admin form sends `?setup=<token>` and strips it from the address bar; from another machine without it, shows "Finish setup on the Mac". Verified: `npm run build`; both screens seen in the browser at the LAN address. Not clicked: submitting the form.
- 2026-11-14 — Split out of `web/`. Verified: `npm run build`; supervisor serves
  the SPA; health and root on scratch port 7421. Not clicked: Start/Stop on
  real apps; full browser pass at 390px.
