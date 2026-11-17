# Mac installer (Apple silicon)

No account, no sudo, no Docker. Three ways in, one installer (`install-starferret.sh`) behind all of them.

**The app (for everyone).** Download `StarFerret.dmg` from the latest release, drag
StarFerret into Applications, open it, click Install. A window shows each step and the
model download. Afterwards StarFerret sits in the menu bar: Open the Board, Open Control,
Check for updates, Repair, Remove. Source: [`app/`](app/), built by `build-dmg.sh`.
Until the app is signed by Apple, releases carry `StarFerret-early-access.dmg`:
macOS asks testers to confirm it once in System Settings. The steps are in
[`early-access.md`](early-access.md), which is also inside the `.dmg` and at the top
of the release notes. Once signed, releases carry `StarFerret.dmg`, which opens with
a double click.

**One Terminal line (for IT people).** `curl` downloads the installer and `bash` runs
it. Same steps, printed in the window. Until the first release is published from this
repo, take the installer from `main`:

```bash
curl -fsSL https://raw.githubusercontent.com/StarFerret/board-admin/main/installer/macos/install-starferret.sh | bash
```

With no release, step 2 downloads the source instead, so the Mac needs Node.js to build
the web pages. After the first release, use
`curl -fsSL https://github.com/StarFerret/board-admin/releases/latest/download/install-starferret.sh | bash`,
which needs no Node.js. The app (`.dmg`) only exists once a release does.

**From a checkout:**

```bash
bash installer/macos/install-starferret.sh
```

## What it does

1. Checks the Mac: Apple silicon, memory, free disk.
2. Downloads StarFerret to `~/.starferret/app` (skipped when run from a checkout). A release download is checked against the release's `SHA256SUMS` when it has one.
3. Sets up a private Python 3.12 with `uv`. Installs `uv` to `~/.local/bin` if missing.
4. Starts Board (7410) and Control (7411) as LaunchAgents, so they come back after a reboot, and opens Control's Models page so the admin can be made while the rest installs.
5. Installs Ollama to `/Applications` if missing (or `~/Applications` when this Mac user cannot write there), and starts it.
6. Installs LibreChat without Docker: a private Node.js, MongoDB (this Mac only, port 27410), LibreChat ready built from the release (or built from its source when the release has none), settings that point it at the local model. Port 3080.
7. Installs n8n without Docker with the same private Node.js. Port 5678.
8. Downloads a model sized to memory (48GB and up `qwen3.8:27b`, 24GB and up `gemma4:latest`, otherwise `gemma4:12b-mlx`, with a warning under 16GB) **through Control**, so the download keeps going if the window is closed and Control's Models page shows it. The window shows progress too. Then it loads the model once to confirm it runs on the GPU and saves it as the Board's model. If Control cannot take the download, it runs in the window as before.
9. Prints local and network addresses, plus a one time link for creating the Control admin from another machine, and opens the Board.

It is safe to run again. It upgrades in place and never touches `data/`.

## Options

| Flag | Effect |
|---|---|
| `--dry-run` | Show every step, change nothing |
| `--model NAME` | Pull this model instead of picking by memory |
| `--no-librechat` | Skip LibreChat |
| `--no-n8n` | Skip n8n |
| `--no-browser` | Do not open the browser at the end |
| `--uninstall` | Stop services and remove LaunchAgents. Keeps data and models |
| `--uninstall --everything` | Also delete `~/.starferret` (programs, data, logs) and the Ollama, uv, and models this installer added. Anything the Mac had before stays. A checkout's own `data/` folder is kept. Waits 10 seconds first in a Terminal. |

The installer notes what it added in `~/.starferret/installed-by-starferret`. That file is how `--everything` knows what to delete.

`STARFERRET_HOME` moves the install location. `STARFERRET_REF` picks a branch or tag.

## Services

| Label | What | Log |
|---|---|---|
| `com.starferret.supervisor` | Control API and UI, port 7411 | `supervisor.log` |
| `com.starferret.board` | Board, port 7410 | `board.log` |
| `com.starferret.librechat` | LibreChat, port 3080 | `librechat.log` |
| `com.starferret.mongodb` | LibreChat's database, port 27410, this Mac only | `mongodb.log` |
| `com.starferret.n8n` | n8n, port 5678 | `n8n.log` |

Logs are in `~/.starferret/logs` for an installed copy, or `data/stack` in a checkout. The summary prints the folder.

Control sees LibreChat and n8n through the `launchd:` field in
`catalog/librechat.yaml` and `catalog/n8n.yaml`, and starts and stops them with `launchctl`.
Everything they need lives under `~/.starferret`: `node/`, `mongodb/`, `librechat/`, `n8n/`.

## Release bundle

A source archive has no built Board or Control UI, so a Mac without Node.js needs
the release bundle (includes `web/dist` and `control-web/dist`).

Pushing a `v*` tag runs [`.github/workflows/release.yml`](../../.github/workflows/release.yml)
on an Apple silicon runner. It uploads:

| File | Made by |
|---|---|
| `starferret-macos.tar.gz` | `build-release.sh`: the app with both web UIs built, and `VERSION` |
| `librechat-<version>-darwin-arm64.tar.gz` | `build-librechat.sh`: LibreChat built for Node.js 24, dev packages removed |
| `install-starferret.sh` | copied by `build-release.sh`, so the one line install matches the bundle |
| `SHA256SUMS` | `build-release.sh`, over everything above |

The installer tries `releases/latest/download/starferret-macos.tar.gz` first and
falls back to the source archive, building the web UI if `npm` is present. For
LibreChat it uses the ready built bundle when the latest release has one for the
pinned `LIBRECHAT_VERSION`, and builds from source otherwise. Both downloads are
checked against `SHA256SUMS`.

The `.dmg` is built by `build-dmg.sh`. With the Apple signing secrets (listed at the
top of `release.yml`) it is `StarFerret.dmg`, signed and notarized. Without them it
is `StarFerret-early-access.dmg`, ad hoc signed, with the opening steps inside.

By hand (needs Node.js 24 and an Apple silicon Mac for LibreChat):

```bash
bash installer/macos/build-librechat.sh
bash installer/macos/build-release.sh v0.1.0
bash installer/macos/build-dmg.sh      # ad hoc signed unless STARFERRET_SIGN_ID is set
gh release create v0.1.0 dist/install-starferret.sh dist/*.tar.gz dist/SHA256SUMS
```

An early access (ad hoc signed) `.dmg` opens with a double click only on the Mac that
built it. Everywhere else, people need the steps in `early-access.md`, an admin
password, and a Mac their company does not lock down. Fine for testers; the public
site should link the signed `StarFerret.dmg`.

## Not done yet

- Publishing the `.dmg` needs an Apple Developer ID (signing and notarization). The app is built; it has no icon yet.
- A LaunchAgent from before the rename is not removed. Stop it by hand if a port stays busy.
