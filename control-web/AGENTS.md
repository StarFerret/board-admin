# control-web/: Control (admin) UI

Read the root [`AGENTS.md`](../AGENTS.md) first, then [`NOTES.md`](NOTES.md).

## Purpose

The React app for **Control** only. Built to `control-web/dist`, served by the
supervisor on port **7411**. Admins manage apps, models, people, capacity, and
updates. This is not the Board and not the marketing site.

## Layout

| Path | What |
|---|---|
| `src/App.jsx` | Routes: `/overview`, `/usage`, `/apps`, `/models`, `/users`, `/machine`, `/updates` |
| `src/pages/` | Control pages |
| `src/components/ControlShell.jsx` | Control chrome; link out to the Board |
| `src/components/ui/` | shadcn-style primitives (copied from `web/`, may drift) |
| `src/controlApi.js` | All API calls under `/api/control` on this same origin |
| `vite.config.js` | Dev server on 5174, proxies `/api` to 7411 |

## Rules

1. **Design for the non technical operator.** One obvious action per screen.
   Plain labels: "Start", "Update", "Add a Mac". No jargon like "container",
   "compose", "daemon", or "inference" in visible text.
1a. **Translate the machine into AI terms.** Say "running slowly", not "62% on
   GPU". Raw machine numbers only on the Machine page.
1b. **Never show available disk space.**
2. **Never show a raw error.** Recover when you can; otherwise say what failed
   and what to do next. No `alert()`, no stack traces.
3. **Every async view has loading, empty, and error states.**
4. **Talk only to this origin** through `controlApi.js`. Never call the Board
   origin from the browser; use Control routes that forward server side
   (`/api/control/board/ollama`).
5. **Works on a phone.** Check at 390px. Touch targets at least 44px.
6. **Use the existing primitives** in `src/components/ui/` and Tailwind tokens
   from `index.css`. Icons are `lucide-react`. Do not add a second icon library.
7. **New user facing text says StarFerret.**
8. **Rebuild for changes to show up:** `npm run build`. `control-web/dist` is
   git ignored.

## Verify

```bash
cd control-web && npm run build
```

Then open `http://127.0.0.1:7411` (or a scratch Control on 7421) and click
through the screen you changed. Update `NOTES.md`.
