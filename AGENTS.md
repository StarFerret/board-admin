# StarFerret (open source): instructions for AI agents and contributors

Read this file first, every session. Then read the `AGENTS.md` and `NOTES.md`
in the folder you are about to change. `CLAUDE.md` files only import the
matching `AGENTS.md`, so Claude Code, Cursor, and other tools all read the same
rules. Edit `AGENTS.md`, never the `CLAUDE.md` stubs.

## 1. This repo is public. Read this before anything else.

This is the **open source** part of StarFerret, under Apache 2.0. Anyone can
read, download, and fork it. Everything you commit here is public for good:
deleting it later does not remove it from forks, clones, or caches.

**What lives here (open):** the Mac installer (`installer/`), Control, the
admin site (`supervisor/` and `control-web/`), and the Board (`server/` and
`web/`), plus the app catalog they run (`catalog/`, `stacks/`). Releases and
the one line install are published from this repo, and installed Macs check
this repo for updates (`REPO` in `installer/macos/install-starferret.sh` and
`supervisor/updater.py`).

**What does not live here (closed):** the marketing site, pricing, sales and
product strategy, customer information, and the team's internal plans. The
StarFerret team keeps those in a separate private repository. Do not add them
here, do not copy files from there into here, and do not link to files that
are only there. If a change here needs a matching change to the marketing site
(for example the installer's step list, or a feature the site marks "Coming
soon"), say so in your report instead.

**Never commit:**

- Personal information: names, personal email addresses, phone numbers, home
  folder paths with a real user name, machine names, IP addresses.
- Secrets: API keys, tokens, passwords, signing certificates, `.env` files.
  The release workflow reads secrets from GitHub by name only.
- Anything from `data/`: databases, workspaces, logs, setup tokens, local keys.
- Customer names, prices, revenue, or sales strategy.

The one contact address in the code is the public `hello@starferret.com`.

Before you commit, scan your diff for the list above. If you find something
already committed, stop and tell the maintainer. Do not try to rewrite history
on your own.

## 2. What StarFerret is

StarFerret turns Apple silicon Macs into a private AI server for a team, so a
company can keep work in the building and cut its cloud token bill. The free
download gets one Mac running in minutes with no account. Companies that want
preloaded Mac clusters, setup, and support buy that from the StarFerret team.

### Free and paid: where the line is

The README has the table people read. These are the rules behind it.

**Free is everything in this repo.** Every feature that exists here works for
any number of people, with no account, no license key, no time limit, and no
phone home. Never add a license check, a seat counter that blocks anything, a
nag screen, a trial timer, or a feature that only works after payment. The
code is Apache 2.0, so a paywall in it would not hold anyway.

**Paid is what the StarFerret team provides around the code:**

- Preloaded, configured Mac Studio hardware.
- Setup and training: install, LibreChat and n8n workflows, training.
- Support, priced per person per year, with updates of the managed stack
  included.
- Clusters of more than one Mac, quoted after a load test.
- Planned and marked "Coming soon": SSO and team management, load balancing
  across Macs, smart routing to frontier models with the customer's own key.

Rules:

- **No prices in this repo.** Not in code, UI, docs, or commit messages.
  Prices change and belong to the closed side. Point people to
  hello@starferret.com.
- **Do not decide on your own where a planned paid feature's code lives.**
  If you are asked to build SSO, team management, load balancing, or smart
  routing, check with the maintainer first whether it goes in this repo.
- **The free product never mentions paid plans in its way.** Control and the
  Board may show one quiet line with the contact address (as the installer's
  last line does). Never put it in front of a task, in an error, or in a
  dialog.
- **Keep the README table true.** When a feature ships, or the paid list
  changes, update the "Free and paid" table in the same change. "Coming soon"
  items stay on `TODO.md` until they ship.

### The install comes first

The install is how everyone meets StarFerret, so treat `installer/` as the
most important code here. A stranger runs one thing, and minutes later their
Mac answers their team. If it fails, asks a question, or needs a password, we
lose them. Before you change anything the installer touches:

- Read `installer/AGENTS.md`. Its rules (bash 3.2, no sudo, dry run for every
  step, works piped, never deletes data) are not optional.
- There are three ways in: the StarFerret app, the one Terminal line, and a
  clone. All three run `installer/macos/install-starferret.sh`. Keep it that
  way.
- If you change what the install asks for, takes, or prints, update the
  README's Install section in the same change.

## 3. Repo map

| Folder | What it is | Stack |
|---|---|---|
| `installer/` | One step Mac installer, the Mac app, and the release build scripts. | bash 3.2, Swift |
| `supervisor/` | **Control**: admin API and Control UI on port 7411. Apps, models, users, machine health, updates. | Python, Flask |
| `control-web/` | Control UI. Built to `control-web/dist`, served by `supervisor/`. | Vite, React, Tailwind, lucide, shadcn |
| `server/` | **Board**: agents, workspaces, chat, files on port 7410. Serves the Board UI. | Python, Flask, Socket.IO |
| `web/` | Board UI. Built to `web/dist`, served by `server/`. | Vite, React, Tailwind, lucide, shadcn |
| `catalog/`, `stacks/` | App manifests and their Docker Compose files. | YAML |
| `.github/workflows/` | `release.yml` builds and publishes a release on a `v*` tag. | GitHub Actions |
| `data/` | Runtime data. Git ignored. **Never commit, never delete.** | |

Other root files: `README.md` (install and run), `DOCS.md` (how the Board
works in code), `TODO.md` (the open source backlog), `LICENSE`.

## 4. Principles

1. **The free install is the product demo.** Anything that adds a step, an
   account, a password prompt, or a prerequisite to the first run is a
   regression. No Docker, no sudo, no terminal knowledge assumed.
2. **Three apps, and we do not rebuild what exists.** LibreChat (chat), n8n
   (automations), and the Board. LibreChat and n8n are installed and linked,
   never reimplemented. Do not add a fourth app.
3. **Built for the person with three jobs.** The operator is an IT lead who
   also runs the network and the laptops, or a non technical user. Plain
   words, one obvious action, no configuration they did not ask for.
4. **Honest about tradeoffs.** Local open models are not as smart as frontier
   models, and a GPU server has more compute. Never write copy or UI that
   hides this.
5. **Local first, cloud when it counts.** Work stays on the Mac by default.
   Frontier APIs are a complement with the user's own key, never required.
6. **No invented facts.** No made up numbers, benchmarks, or capacity claims
   in code, UI, or docs. Mark a planning estimate as an estimate.
7. **Do not promise what is not built.** Mark it "Coming soon" and add it to
   `TODO.md`.

## 5. Hard rules

- **Never push, tag, or publish a release unless the maintainer says so.**
  A `v*` tag publishes a release that every installed Mac can update to.
- **Commit only when asked.**
- **Never download a model, or anything else measured in gigabytes, unless
  asked.** That covers `ollama pull`, Control's model pull route, Docker
  images, and running the real installer. Use `--dry-run`.
- **MLX builds only.** Every model StarFerret ships or recommends is an MLX
  build. No GGUF / llama.cpp models in the ladder, the installer, or docs.
  Check with `/api/tags`.
- **Never touch `data/`** except through the app.
- **Do not kill processes on ports 7410, 7411, 3080, 5678, or 11434** without
  asking. Someone's StarFerret may be running.
- **Do not add a dependency** when a few lines of code or an existing one does
  the job. Never add a paid service, an account requirement, or telemetry.
- **Docker and installer privileges stay out of the Board.** Control
  (`supervisor/`) owns them. The Board (`server/`) must not shell out to
  Docker or launchctl.
- **Do not bring back the previous product name.** Identifiers are StarFerret:
  cookie `starferret_control`, browser storage `starferret_name` and
  `starferret_control_token`, Compose prefix `starferret-`, env
  `STARFERRET_HOST` and `STARFERRET_CMD_TIMEOUT`. An existing install signs
  in to Control again, and Board users retype their display name once. A
  Docker app started under the previous prefix has to be stopped by hand.
- **No prices, license checks, or paywalls.** See section 2.
- **Do not stall on small decisions.** Pick a sensible option, say what you
  picked, keep going.

## 6. How to work here

1. Read this file, then the target folder's `AGENTS.md` and `NOTES.md`.
2. Check `TODO.md` for the item you are doing.
3. Make the smallest change that does the job. Match the code around it.
4. Verify it for real (commands are in each folder's `AGENTS.md`). A build
   passing is not the same as the feature working. Say exactly what you ran
   and what you did not test.
5. Update the docs in the same change (section 7).
6. Report plainly: what changed, what was verified, what is still open.

```bash
# Board and Control (from repo root, venv active)
python -m server          # Board on 7410
python -m supervisor      # Control API + UI on 7411

# UIs
cd web && npm install && npm run build              # → web/dist
cd control-web && npm install && npm run build      # → control-web/dist

# Installer, safe
bash installer/macos/install-starferret.sh --dry-run
```

There is no test suite yet. Verification is: build, run, and exercise the
change by hand or with a short script.

## 7. Keeping the docs alive

Every folder with code has three files:

| File | Purpose | Who edits |
|---|---|---|
| `AGENTS.md` | Stable rules and a map of the folder. | Edit when a rule or the structure changes. |
| `NOTES.md` | Living state: what works, what is broken, decisions, next steps. | **Update at the end of every task that touches the folder.** |
| `CLAUDE.md` | One line import of `AGENTS.md`. | Never. |

Rules for `NOTES.md`:

- Keep **Status** and **Known gaps** true. Stale notes are worse than none.
- Add a dated line to **Decisions** when you choose between real options,
  with the reason.
- Add a dated line to **Log** for each finished task: what, and how it was
  verified. Newest first. Trim entries older than about 20.
- Absolute dates (2026-11-15), never "today".
- No code or diffs. Point at the file.
- These notes are public too. Section 1 applies to them.

Also update `TODO.md` when you finish, start, or discover an item, and
`README.md` or `DOCS.md` when run steps or behavior change.

## 8. Where things stand (2026-11-15)

- The code moved here from the team's private repository on 2026-11-15,
  without its history. No release has been published from this repo yet.
- Installer: dry run tested only. No full install has run on a clean Mac.
- Not built: smart routing, clustering and load balancing, SSO.

The per folder `NOTES.md` files and `TODO.md` are the source of truth after
this date.
