# installer/ notes

Living file. Update it at the end of every task that touches this folder.
Rules for this file are in the root `AGENTS.md`, section 6.

## Status (2026-11-14)

- **Releases now come from this public repo** (2026-11-15). The earlier v0.1.0 was published before the code moved here and is not in this repo's releases. No release has been made here yet, so the one line install and the app's update check find nothing until the first `v*` tag. GitHub Actions has not run for StarFerret repos so far (every run ended in `startup_failure`); if `release.yml` does not start here either, build with `build-release.sh` and `build-dmg.sh` on a Mac and upload by hand.
- **StarFerret Mac app and `.dmg` are built** (`macos/app/`, `macos/build-dmg.sh`): install window with steps and a model download bar, then a menu bar item (Open the Board, Open Control, Check for updates, Repair, Remove). It runs the bundled `install-starferret.sh` with `STARFERRET_BUNDLE` (its own copy of StarFerret, so step 2 downloads nothing) and `STARFERRET_GUI=1`. Ad hoc signed only; publishing waits on an Apple Developer ID. The release workflow builds and uploads it only when the signing secrets exist.
- New order (plan step 5): Board and Control start at step 4 and Control's Models page opens; Ollama, LibreChat, n8n follow; the model downloads last, through Control, with progress in the window. The Board's model is saved after the download.
- Ollama falls back to `~/Applications` when `/Applications` is not writable.
- A release download is checked against the release's `SHA256SUMS` (mismatch stops, missing file warns). No release has one yet; step 4 of the plan adds it.
- The summary prints a one time `?setup=` link for creating Control's first admin while `data/control/setup-token` exists.
- Builds both `web/dist` and `control-web/dist` when missing. Summary prints
  Board and Control as two addresses. Release bundle copies both dists.
  Updater requires `control-web/dist/index.html`.

## Status (2026-11-09)

- `macos/install-starferret.sh` is written: eight steps, `--dry-run`, `--model`,
  `--no-open-webui`, `--no-browser`, `--uninstall`.
- **Only dry run tested.** No real install has ever run, on any Mac.
- Verified: syntax under bash 3.2, dry run from a checkout, dry run piped,
  bad flag exits 2, uninstall dry run, generated plist passes `plutil -lint`.
- Never executed: app download and extract, `uv` install, venv creation,
  Ollama download, model pull, `launchctl bootstrap`, Open WebUI install,
  the health waits, the final summary.

## Known gaps

- The Mac app's window was checked by eye on 2026-11-14, with the stand-in script ("It looked right"). Not yet seen against the real installer.
- The app has no icon (it uses the `sparkles` symbol in the menu bar) and does not start at login. The services do, through their LaunchAgents.
- The app needs macOS 13 or newer (`MenuBarExtra`).
- Signing and notarization in CI are written but have never run.
- The early access opening steps (`early-access.md`) are written from how macOS 15 behaves and have not been walked through on a second Mac.
- **Steps 7 and 8 (LibreChat, n8n) are dry run and syntax tested only.** Never
  executed: the Node.js download and checksum, the MongoDB download and start,
  the LibreChat download, `npm ci`, the front end build, the generated `.env`
  and `librechat.yaml`, `npm install` of n8n, and all four new LaunchAgents.
  Checked without downloading: every URL answers, the versions exist for Apple
  silicon, and the settings names match LibreChat v0.8.8's own example file.
- Ready built LibreChat is written (2026-11-14) but has never been built or
  installed. Unknowns: whether `npm prune --omit=dev` keeps everything
  LibreChat needs at runtime, and the bundle size (GitHub's limit is 2 GB per
  file). Until a release carries it, installs still build from source, about
  ten minutes.
- LibreChat's address is set to `<Mac name>.local`. Whether sign in works when
  people open it by IP address instead has not been tried.
- `librechat.yaml` uses config version 1.2.1; v0.8.8 ships 1.3.17 and may log a warning.
- People's first LibreChat visit asks them to register. The first account is the admin.

- The under 24GB choice is now `gemma4:12b-mlx` (about 7.7GB per Ollama's
  library page). Not yet pulled on a real Mac: confirm `/api/tags` shows it as
  MLX and that it runs fully on the GPU on a 16GB Mac.
- **New Metal steps are dry run and parse tested only:** the Rosetta stop in
  step 1, and in step 5 loading the model once and reading `/api/ps` to confirm
  it is fully on the GPU. The same check was done by hand against a live
  Ollama on 2026-11-11 and read 100%.
- Ollama is left at its defaults: context 4096, automatic parallel requests.
  The capacity estimates assume about 8K context. Not set yet.
- **No release bundle is published.** A source archive has no `web/dist`, so a
  Mac without Node.js fails at step 2. Pushing a `v*` tag runs
  `.github/workflows/release.yml`, which needs the repo on GitHub with Actions
  (owner action). The workflow has never run.
- **Not signed or notarized.** Needs an Apple Developer ID. Until then the
  install is a terminal command, which is a real drop off point for this buyer.
- **Memory to model table is a guess:** 48GB and up `qwen3.8:27b`, 24GB and up
  `gemma4:latest`, else `gemma4:12b-mlx` (warns under 16GB). Needs real testing.
- `uv tool install --upgrade open-webui` has not been run; flag spelling is unverified in practice.
- Assumes paths have no `&`, `<`, or `>` (plist values are not XML escaped).
- LAN address uses `en0` then `en1`. A Mac on another interface gets no share link.
- No Windows or Linux path. Deferred on purpose.
- Installs made before 2026-11-15 have no install record, so `--everything` on them removes only `~/.starferret` and the services, not Ollama, uv, or models.
- The Mac app's Remove menu still runs plain `--uninstall`. It has no full removal option yet.
- Dry run output, cosmetic only: with `--no-browser` it still says "would open" the Board at step 9, and "would download a private Node.js" prints in both step 6 and step 7.

## Decisions

- 2026-11-15 — Identifiers use the StarFerret names, with no fallback to the previous ones, so the public source does not contain them. An existing install signs in to Control again, Board users retype their display name once, and a Docker app started under the previous prefix is stopped by hand. Env vars are `STARFERRET_HOST` and `STARFERRET_CMD_TIMEOUT`.
- 2026-11-15 — Owner: `install.sh` is too generic a name for a file strangers download. Renamed to `install-starferret.sh` everywhere (script, build scripts, workflow, Mac app resource, docs). Older dated plans keep the old name.
- 2026-11-15 — Full removal is a separate `--uninstall --everything`, not a change to `--uninstall`, so the command people expect to be safe never deletes chats and workspaces. It removes only what the installer recorded adding; Ollama and uv that were already on the Mac stay, and only the models StarFerret pulled are removed from them. A checkout's `data/` is never deleted (it is the working data).
- 2026-11-15 — Owner asked for a non GGUF model under 24GB. Picked `gemma4:12b-mlx`: Ollama publishes it as an MLX build, it is the same family as the 24GB pick, and at about 7.7GB it leaves room to work on a 16GB Mac. `gemma4:e4b-mlx` was the other candidate, but Ollama lists it larger (9.5GB) for a smaller model. Under 16GB the installer warns instead of stopping, since an 8GB Mac may still load it slowly.
- 2026-11-14 — Owner: ship an early access `.dmg` until the app is signed. Without the Apple secrets, `build-dmg.sh` makes `StarFerret-early-access.dmg` with "How to open StarFerret.txt" inside, and the workflow publishes it with the same steps at the top of the release notes.
- 2026-11-14 — The app is SwiftUI built with `swiftc` from the command line tools, no Xcode project, so CI and any Mac with the tools can build it. It is a menu bar app (`LSUIElement`) because StarFerret runs in the background; the window opens at launch.
- 2026-11-14 — Install starts on a button, not on opening the app, because it downloads 5 to 17 GB.
- 2026-11-14 — The app carries a full copy of the release bundle, so it works without the GitHub release for StarFerret itself (LibreChat, n8n, Ollama, and the model still download).
- 2026-11-14 — Release runner is `macos-15`, not the plan's `macos-14`: both are Apple silicon and 15 will be supported longer. Change it if GitHub retires it.
- 2026-11-14 — LibreChat bundle is built with Node.js 24 to match the installer's private Node.js, because native modules only load on the Node.js line they were built for.
- 2026-11-09 — `uv` manages Python. A test Mac had a Python newer than 3.12, and Open
  WebUI needs 3.11 or 3.12, so the system Python cannot be trusted.
- 2026-11-09 — Open WebUI runs natively, not in Docker. Docker Desktop is a
  licensed, admin level install and would break "no account, no sudo".
- 2026-11-09 — The Board opens at the end, not Open WebUI, because the Board
  only asks for a display name while Open WebUI asks for an admin sign up.
- 2026-11-09 — Board runs as its own LaunchAgent (`python -m server`) rather
  than being started by the supervisor, so it survives a reboot by itself.
- 2026-11-09 — Plists are generated inline, not from a template file, so the
  piped install does not depend on files it has not downloaded yet.
- 2026-11-09 — Ollama is installed by copying the official app to
  `/Applications`, and its bundled binary is called by full path. Ollama's
  own script symlinks into `/usr/local/bin`, which can prompt for a password.
- 2026-11-09 — Busy ports stop the install with a message. It never kills
  another program.

- 2026-11-12 — Owner: three apps only. Open WebUI is removed from the
  installer; LibreChat and n8n are installed natively with a private Node.js.
- 2026-11-12 — LibreChat is built from its tagged source on the customer's Mac
  because it publishes no prebuilt Mac bundle. Versions are pinned (LibreChat
  v0.8.8, MongoDB 8.0.13, Node.js 24, n8n 2) so installs are repeatable.
- 2026-11-12 — MongoDB listens on port 27410 and on this Mac only, so it cannot
  collide with a MongoDB the customer already runs and is not on the network.
- 2026-11-12 — `SESSION_COOKIE_SECURE=false` for LibreChat and
  `N8N_SECURE_COOKIE=false` for n8n, because the office network is plain http
  and browsers would otherwise drop the sign in cookie.

## Next up

1. Real install on a clean Apple silicon Mac (or a fresh user account). Fix what breaks.
2. Publish the release bundle.
3. n8n without Docker (a private Node.js plus `npx n8n` is the likely route).
4. Decide the Open WebUI first run question with the owner.
5. Signed `.pkg` or `.dmg`.

## Log

- 2026-11-15 — Installer identifiers use the StarFerret names. A LaunchAgent from before the rename is no longer removed. Machine notes in this file say "a test Mac". Verified with `bash -n`.
- 2026-11-15 — Moved to the public open source repo `StarFerret/board-admin`. `REPO` in `install-starferret.sh` and `supervisor/updater.py` now points here, so releases and updates come from this repo. Verified: syntax and a dry run from this repo with the macOS stand-ins.
- 2026-11-15 — Added `--uninstall --everything` and the install record (`remember`), and renamed the script to `install-starferret.sh`. Verified on Linux with macOS stand-ins and throwaway HOMEs: `--everything` alone exits 2; plain uninstall keeps data; dry run deletes nothing; a real run deletes Ollama, its models, uv, and `~/.starferret` when the record says StarFerret added them and leaves an unrelated file; with Ollama there before, it keeps Ollama and uv and runs `ollama rm` only for the recorded models; `STARFERRET_HOME=$HOME` is refused; `remember` skips duplicates and writes nothing in a dry run. Not verified: quitting Ollama with `osascript` on a real Mac, the Mac app with the renamed resource (needs `build-dmg.sh` on a Mac).
- 2026-11-15 — Under 24GB model changed from `deepseek-r1:8b` to `gemma4:12b-mlx`, with a warning under 16GB. Verified: dry runs at 8, 16, 24, 48 GB with the macOS stand-ins pick the right model and print the warning only at 8GB. Not verified on a Mac.
- 2026-11-14 — Dry run test on Linux with stand-ins for the macOS commands (`uname`, `sysctl`, `df -g`, `launchctl`, `lsof`, `open`) and a throwaway HOME, under bash 5.2 (building bash 3.2 was not allowed in that session). Passed: syntax, checkout and piped dry runs (nothing written, only read only `launchctl print`/`lsof`/GET calls), uninstall dry run, bad flag and `--model` with no name exit 2, Linux/Intel/Rosetta refusals, memory to model choice at 8/16/24/48/64 GB, low disk and busy port warnings, bundle present and missing, `--no-librechat --no-n8n`. Also ran the real `write_plist` (parses with plistlib) and `check_sha256` (match, mismatch, not listed, `*` prefix). Not run: anything on a Mac, bash 3.2 itself, a real install.
- 2026-11-14 — Merged to `main`, tagged and published v0.1.0 by hand after Actions failed to start. Verified: downloaded all four release files back with `gh release download` and `shasum -c` passed; `releases/latest` is v0.1.0.
- 2026-11-14 — Early access `.dmg`: `early-access.md`, unsigned naming and instructions in `build-dmg.sh`, workflow builds and publishes it when the signing secrets are missing. Verified: a real `build-dmg.sh` run (420 KB, holds the app, the Applications link, and the instructions; `shasum -c` passes) and the publish step run with a stand-in `gh` (right files, notes start with the steps and end with the Terminal line). Not verified: that `gh` keeps our notes when `--generate-notes` is also passed, the opening steps on a second Mac.
- 2026-11-14 — Owner previewed the app window with `app/fake-install.sh` and said it looked right.
- 2026-11-14 — Built the StarFerret Mac app and `build-dmg.sh`, added the signed `.dmg` to the release workflow, `STARFERRET_BUNDLE` and `STARFERRET_GUI` to `install-starferret.sh`, and moved the Terminal line to the release URL. Verified: parser test (9 cases, found and fixed two bugs), `build-release.sh` then `build-dmg.sh` (416 KB `.dmg`; mounted read-only it holds the app, an Applications link, `install-starferret.sh`, the bundle; ad hoc signature valid; `shasum -c` passes), the app run against a stand-in script (window on screen, bundle path and GUI mode passed, all output logged, exit 0; exit 1 shows no crash), workflow YAML parses, `bash -n`. Not done: looking at the window, signing, notarization, a real install.
- 2026-11-14 — Plan step 5: reordered steps, model download through Control with the local key, Board model saved after the download. Verified: step 8 run alone against a scratch Control and fake Ollama (download to ready, Ollama error, unknown name, and fallback without a key), dry runs from a checkout, piped, with `--no-librechat --no-n8n`, with `--no-browser`, uninstall, bad flag, no LaunchAgents made. Not tested: the redrawn progress line in a real terminal (the run was piped), a real install.
- 2026-11-14 — Plan step 4: `build-librechat.sh`, checksums and `install-starferret.sh` in `build-release.sh`, `.github/workflows/release.yml`, installer prefers ready built LibreChat. Verified: `bash -n` on all three scripts, version read from `install-starferret.sh` (v0.8.8), workflow parses as YAML, `build-release.sh v0.0.0-test` ran and `shasum -c` passed (output deleted), `verify_release_file` with a stand-in curl (match, mismatch stops, no file, not listed), installer dry runs. Not run: `build-librechat.sh` (1 to 2 GB download, blocked and needs the owner), the workflow, a real install.
- 2026-11-14 — Plan step 2: Ollama `~/Applications` fallback, release checksum check, setup link in the summary, step list synced (README, AGENTS, site mock). Verified: the new functions on fake folders and sums under /bin/bash 3.2 (writable, read only, both unwritable, right, wrong, `*name`, missing), the link print with and without a token file, `bash -n`, dry run, piped dry run, uninstall dry run, bad flag exit 2, no LaunchAgents created. No real install, no Ollama download.
- 2026-11-14 — Reviewed the installer for a public one click install and wrote a step by step plan for it. Verified: `bash -n`, a dry run, and logged out `curl -I` on the repo, raw script and release URL (all 404). No code changed.
- 2026-11-14 — Installer builds Control UI too; summary prints two URLs; release
  and updater require `control-web/dist`. Verified: bash -n; dry-run aborted on
  Linux (expected). Not run: real Mac install.

- 2026-11-12 — Replaced the Open WebUI step with native LibreChat (step 7) and n8n (step 8). Verified by `bash -n`, dry runs with and without `--no-librechat` and `--no-n8n`, uninstall dry run, bad flag exit 2, and upstream URL and version checks. No real run.
- 2026-11-11 — Added a Rosetta check and a "model is on the GPU (Metal)" check after the model pull. Verified by `bash -n`, a dry run, and the parsing against real `/api/ps` output.
- 2026-11-09 — Replaced the LaunchAgent scaffolding with the one step installer and added `build-release.sh`. Verified by dry runs only.
