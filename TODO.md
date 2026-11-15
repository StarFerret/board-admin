# To do

The open source backlog for the installer, Control, and the Board, ordered by
how much the free download depends on it. Section numbers are referenced from
the folder notes, so keep them.

## 0. Three apps only: LibreChat, n8n, and the Board

- [x] Installer installs **LibreChat** with no Docker. **Dry run only.**
- [x] Installer installs **n8n** with no Docker. **Dry run only.**
- [ ] **Run the LibreChat and n8n steps for real** on a Mac (several GB of downloads and a ten minute build). Fix what breaks.
- [ ] Ship LibreChat prebuilt so the install does not wait for a build. `installer/macos/build-librechat.sh` and the release workflow are written; never built.
- [x] `catalog/`: Board, LibreChat, n8n, and nothing else.
- [ ] **API for code editors:** make the model address reachable on the office network, with a key, and show the address in Control.
- [ ] Control → People reads LibreChat accounts (they live in MongoDB). Today chat users are not counted.

## 1. The free download has to feel instant

- [x] One step installer: `installer/macos/install-starferret.sh`. No clone, no venv, no sudo, no Docker.
- [x] Default model picked from installed memory.
- [x] Print the LAN address so the team can open it.
- [x] Control understands apps the installer runs natively (`launchd:` in the catalog).
- [x] Control's first admin can only be made from the Mac or with the installer's one time setup link.
- [x] `--uninstall --everything` removes StarFerret and only what it added.
- [ ] **Publish the first release from this repo** (`v*` tag, `.github/workflows/release.yml`). Until then the one line install and the update check find nothing, and a Mac without Node.js cannot install from source.
- [ ] Run a full install on a clean Mac. So far it has only been dry run tested.
- [ ] Signed and notarized `StarFerret.dmg`. The app and `build-dmg.sh` are built; signing needs a Developer ID in the release secrets.
- [ ] App icon for StarFerret.app.
- [ ] Mac app: a "Remove everything" choice in the Remove dialog that runs `--uninstall --everything`.
- [ ] Walk through `installer/macos/early-access.md` on a second Mac with the first early access release.
- [ ] Tune the memory to model table with real load tests.
- [ ] Board: click a file to preview or download it; drag and drop upload.
- [ ] Board: example jobs in an empty agent chat ("Summarize this file into a Word doc").
- [ ] Board: plain words for "Steer", "Interrupt", "How hard / tries", "Context".

## 2. Smart routing to frontier models

Marked "Coming soon". Local by default, cloud with the user's own key when it counts.

- [ ] Let an admin add an Anthropic, OpenAI, or Google API key in Control. Store it encrypted on the machine.
- [ ] One OpenAI compatible endpoint for every app in the catalog, so LibreChat, n8n, and the Board route the same way.
- [ ] Routing policy: local by default, cloud when the user picks a frontier model, when a request is flagged hard, or when local fails or the queue is too deep.
- [ ] Per workspace switch to forbid cloud routing, for data that must stay in the building.
- [ ] Spend view: requests kept local against requests sent out.
- [ ] Monthly cloud budget cap with an alert.

## 2b. Usage and admin (who is using AI)

- [x] Record Board usage per turn: person, agent, folder, model, tokens.
- [x] Control → Usage: people, messages, tokens, per day, by folder, by model.
- [x] Control → Apps shows everything installed, the Board included.
- [ ] Count usage from the other apps and the API. Needs the shared endpoint in section 2.
- [ ] Real identity. People are typed display names today.
- [ ] Export usage (CSV) for a monthly report.
- [ ] Per person or per folder limits, and turning a person off.
- [ ] Decide how long usage is kept. Nothing is trimmed today.
- [ ] Plain wording pass on Control → Machine, Models, Users, Updates.

## 3. Rename to StarFerret

- [x] Page titles, package names, the Control cookie, browser storage, the Compose prefix, and env vars say StarFerret (2026-11-15). An existing install signs in to Control again, Board users retype their display name once, and a Docker app started under the previous prefix is stopped by hand. Env vars are `STARFERRET_HOST` and `STARFERRET_CMD_TIMEOUT`.

## 4. Catalog apps (three only)

- [x] Board, LibreChat, n8n in Control → Apps.
- [ ] Verify start, stop, open, and health for all three from Control on a real Mac.
- [ ] Pin app versions once verified.

## 4b. Admin panel (Control)

- [x] Control is its own site on 7411 with its own folder `control-web/`.
- [x] Capacity is a real load test: memory per conversation, then up to 8 questions at once, three runs each, averaged.
- [x] Real load recorded per minute for 30 days and shown as averages on Overview.
- [x] Failover ladder is MLX only: `qwen3.8:27b` → `gemma4:latest` → `gemma4:12b-mlx`.
- [ ] Confirm on a real Mac that `gemma4:12b-mlx` reports as MLX in `/api/tags` and fits a 16GB Mac with room to work.
- [ ] Have the installer and Control → Models refuse or warn on a model that is not MLX.
- [ ] Measure memory per conversation for MLX models. Ollama reports a flat figure for them.
- [ ] Raise the capacity test ceiling above 8 at once.
- [ ] Failover should not persist a downgrade caused by memory being busy for a moment.
- [ ] Failover auto-pulls missing ladder models (gigabytes) with no prompt. Decide whether it should ask an admin first.
- [ ] Measure people per answer slot from real usage. It is a planning estimate (10) in `supervisor/capacity.py`.
- [ ] Set Ollama for a team in the installer: parallel requests, context length (default 4096; the capacity estimates assume about 8K), keep the model loaded.
- [ ] Run the capacity test from the installer so Overview is never empty on day one.
- [ ] Usage per person and per model: requests, tokens, tokens per second, time waiting.
- [ ] Queue depth and people mid generation: the number that says "add a Mac".
- [ ] Real accounts on the Board, so an admin can remove a person.
- [ ] Count real questions and waiting time instead of inferring "answering" from GPU load.
- [ ] Alerts: disk nearly full, memory pressure, a model not fully on the GPU, an app down.
- [ ] Audit log of admin actions.
- [ ] Backup and restore of `data/`.
- [ ] Updates page: real updates for Board, Control, and the native apps.
- [ ] Control listens on every network interface with open CORS and plain http. Review before a company install.

## 5. Cluster

- [ ] Link several Macs and load balance requests across them.
- [ ] Cluster view in Control: each node, its load, its models, its health.
- [ ] Keep serving when one node drops.
- [ ] Load test tool to size a cluster from real work.

## 6. Support tooling

- [ ] Remote model and app updates on a schedule, with rollback.
- [ ] MCP setup helpers for common company tools.
- [ ] Health report readable remotely, with the user's consent.
