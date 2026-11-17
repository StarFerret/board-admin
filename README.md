# StarFerret

**Private AI for your team, on your own Mac.** Free and open source (Apache 2.0).

StarFerret turns an Apple silicon Mac into an AI server for the people in your
office. One installer sets up everything, with no account, no sign in, no
Docker, and no admin password:

- **The Board**: shared folders with named AI agents living in them. People
  drop files in, and agents read, write, and run things there.
- **LibreChat**: chat for everyone, with accounts and saved conversations.
- **n8n**: automations that connect your tools and let AI do the repeat steps.
- **Control**: the admin site. Start, stop, and check the apps, manage models
  and admins, and see how busy the Mac is.
- **A local model** through [Ollama](https://ollama.com), sized to your Mac's
  memory, running on its GPU. MLX builds only.

Your work stays on your Mac. Nothing is sent to us.

**Be honest with yourself about the tradeoffs.** Local open models are not as
smart as the best cloud models, and one Mac has less compute than a GPU
server. StarFerret is for work that should stay in the building, and for
cutting a cloud AI bill, not for replacing frontier models everywhere.

---

## Install

### What you need

| | |
|---|---|
| Mac | Apple silicon (M1 or newer). Intel Macs are not supported. |
| macOS | macOS 13 or newer for the StarFerret app. The Terminal install has no other requirement. |
| Memory | 16GB or more. Under 16GB it installs, but the model may be slow or not load. |
| Free disk | About 30GB for the model, LibreChat, and n8n. |
| Internet | For the install only. It downloads several GB, mostly the model. |
| Account | None. No sudo, no password prompt, no Docker. |

The model is picked from your Mac's memory:

| Memory | Model |
|---|---|
| 48GB or more | `qwen3.8:27b` |
| 24GB to 47GB | `gemma4:latest` |
| Under 24GB | `gemma4:12b-mlx` |

Pick another one with `--model NAME`.

### Choose how to install

> **Before the first release:** options 1 and 2 download from this repo's
> latest release, and none has been published yet. Until then use option 3.

**1. The StarFerret app (for everyone).** Download `StarFerret.dmg` from the
[latest release](https://github.com/StarFerret/board-admin/releases/latest),
drag StarFerret into Applications, open it, and click **Install**. A window
shows each step and the model download. Afterwards StarFerret lives in the
menu bar: Open the Board, Open Control, Check for updates, Repair, Remove.

Until the app is signed by Apple, releases carry
`StarFerret-early-access.dmg` instead, and macOS asks you to confirm it once
in System Settings. The steps are in
[`installer/macos/early-access.md`](installer/macos/early-access.md).

**2. One Terminal line (for IT people).** Same steps, printed in Terminal:

```bash
curl -fsSL https://raw.githubusercontent.com/StarFerret/board-admin/main/installer/macos/install-starferret.sh | bash
```

No release has been published from this repo yet, so this runs the installer
from `main` and it downloads the source. Like a clone, that needs Node.js
installed, because the source has no prebuilt web pages. Once the first
release is out, the line becomes
`curl -fsSL https://github.com/StarFerret/board-admin/releases/latest/download/install-starferret.sh | bash`
and Node.js is no longer needed.

**3. From a clone of this repo.**

```bash
git clone https://github.com/StarFerret/board-admin.git
cd board-admin
bash installer/macos/install-starferret.sh --dry-run   # shows every step, changes nothing
bash installer/macos/install-starferret.sh
```

A clone has no prebuilt web pages, so this needs Node.js installed. The
installer builds them on the first run.

### What happens

1. Checks the Mac: Apple silicon, memory, free disk.
2. Gets StarFerret (skipped when you run it from a clone).
3. Sets up a private Python. Nothing is installed system wide.
4. Starts the Board and Control, and opens Control so you can create the
   admin while the rest installs.
5. Installs Ollama if it is missing, and starts it.
6. Installs LibreChat and its database. No Docker.
7. Installs n8n. No Docker.
8. Downloads the model. This is the long part. It keeps going if you close the
   window, and Control's Models page shows the progress.
9. Opens the Board and prints the addresses.

Everything starts again on its own after a reboot. Running the installer again
is safe: it upgrades in place and never touches your data.

### After the install

| App | On this Mac | Port |
|---|---|---|
| Board | http://127.0.0.1:7410 | 7410 |
| Control | http://127.0.0.1:7411 | 7411 |
| LibreChat | http://127.0.0.1:3080 | 3080 |
| n8n | http://127.0.0.1:5678 | 5678 |

- **Create the Control admin** at step 4, or with the one time link the
  installer prints at the end. That link also works from another computer.
- **Share with your team:** the installer prints this Mac's network address.
  People on the same network open the Board, LibreChat, and n8n there.
- **LibreChat's first account is its admin.** Everyone else registers.

### If something goes wrong

- **"Port 7410 is already in use"**: another program is using it. The
  installer never stops programs it did not start. Quit that program, or find
  it with `lsof -nP -iTCP:7410 -sTCP:LISTEN`, and run the installer again.
- **"This Terminal is running under Rosetta"**: open Terminal normally (Get
  Info, untick "Open using Rosetta") and run it again.
- **Logs** are in `~/.starferret/logs` (or `data/stack` in a clone). The
  installer prints the folder.
- **Repair:** run the installer again, or choose Repair in the menu bar app.

All flags, services, and logs: [`installer/macos/README.md`](installer/macos/README.md).

### Update

Open Control → **Updates** (the menu bar app's **Check for updates** opens
it). It checks this repo's latest release and updates in one click, keeping
your data, and can go back one version if the new one does not start. A copy
installed from a clone updates with `git pull` and the installer instead.

### Remove

```bash
bash installer/macos/install-starferret.sh --uninstall               # stop StarFerret, keep your data
bash installer/macos/install-starferret.sh --uninstall --everything  # delete StarFerret and what it added
```

`--everything` deletes StarFerret's programs and data, and the Ollama, uv, and
models the installer added. Anything that was on your Mac before stays. It
deletes everyone's chats, Board folders, and automations, so it waits 10
seconds first. Add `--dry-run` to see the list without deleting anything.

---

## Free and paid

**Everything in this repository is free**, for any number of people, with no
account, no license key, and no time limit. That includes every feature that
exists today. Companies that want StarFerret run for them pay the StarFerret
team for hardware, setup, and support.

| | Free (this repo) | Paid (from the StarFerret team) |
|---|---|---|
| Installer and StarFerret app | ✓ | ✓ |
| The Board | ✓ | ✓ |
| LibreChat and n8n, installed and linked | ✓ | ✓ |
| Control for one Mac: apps, models, admins, usage, capacity | ✓ | ✓ |
| Local models, updates from public releases | ✓ | ✓ |
| Preloaded, configured Mac Studio hardware | | ✓ |
| Setup and training: we install it, set up your LibreChat and n8n workflows, and train your team | | ✓ |
| Support: one contact for install help, phone or remote, and extending workflows. Priced per person, per year, with updates of the managed stack included. | | ✓ |
| Clusters: more than one Mac, sized after a load test | | ✓ (quote) |
| SSO (company login) and team management | | Coming soon |
| Load balancing across several Macs | | Coming soon |
| Smart routing: local by default, a frontier model with your own API key when it counts | | Coming soon |

"Coming soon" means it is not built yet, here or anywhere. It is on
[`TODO.md`](TODO.md).

Prices are not in this repo. Ask at **hello@starferret.com**.

---

## Develop

Needs Python 3.10+, Node.js 18+, and Ollama locally or on the network. Runs on
any OS for development; the installer is Mac only.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r server/requirements.txt
(cd web && npm install && npm run build)
(cd control-web && npm install && npm run build)

python -m server       # Board on http://127.0.0.1:7410
python -m supervisor   # Control on http://127.0.0.1:7411
```

UI dev mode: `cd web && npm run dev` (port 5173) or
`cd control-web && npm run dev` (port 5174). Both proxy `/api` to the running
Python servers.

| Variable | Default | Purpose |
|---|---|---|
| `PORT` | `7410` | Board port |
| `CONTROL_PORT` | `7411` | Control port |
| `OLLAMA_MODEL` | `qwen3.8:27b` | Model used until one is saved |

How the Board works (agents, folders, tools, web search, failover):
[`DOCS.md`](DOCS.md).

## Contributing

Issues and pull requests are welcome. Read [`AGENTS.md`](AGENTS.md) first,
whether you are a person or an AI agent. It has the rules for this repo,
including what must never be committed. The backlog is [`TODO.md`](TODO.md).

## License

Apache 2.0. See [`LICENSE`](LICENSE).
