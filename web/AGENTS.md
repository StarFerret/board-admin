# web/: the Board UI

Read the root [`AGENTS.md`](../AGENTS.md) first, then [`NOTES.md`](NOTES.md).

## Purpose

The React app for the **Board** only. Built to `web/dist`, served by the Board
server on port **7410**. Folders, agents, chat, Settings. Control lives in
[`../control-web/`](../control-web/) on port 7411.

**This is not the marketing site.** The site is kept elsewhere and has its own
design. Do not copy styles across.

## Layout

| Path | What |
|---|---|
| `src/App.jsx` | Routes: `/` board, `/w/:id` folder, `/a/:id` agent chat, `/settings` |
| `src/pages/` | Board pages |
| `src/components/` | `AppShell`, `ShareSheet`, and `ui/` primitives (shadcn style) |
| `src/api.js` | Board API calls; `getControlUrl()` builds the Control site address |
| `src/useSocket.js` | Socket.IO hook for live updates |
| `vite.config.js` | Dev server on 5173, proxies `/api` and `/socket.io` to 7410 |

## Rules

1. **Design for the non technical operator.** One obvious action per screen.
2. **Never show a raw error.** Recover when you can; say what failed and what
   to do next. No `alert()`.
3. **Every async view has loading, empty, and error states.**
4. **The Board UI talks only to the Board origin through `api.js`.** It links
   to Control with a plain `<a href>` (or `window.location`) built by
   `getControlUrl`. It never calls `/api/control` or port 7411.
5. **Live data comes over the socket.** Do not add polling where a Socket.IO
   event exists.
6. **Works on a phone.** Check at 390px. Touch targets at least 44px.
7. **Use the existing primitives** in `src/components/ui/` and Tailwind tokens
   from `index.css`. Icons are `lucide-react`.
8. **New user facing text says StarFerret.**
9. **You must rebuild for changes to show up:** `npm run build`.

## Verify

```bash
cd web && npm run build
```

Then look at it on `http://127.0.0.1:7410` (or scratch 7420). Update `NOTES.md`.
