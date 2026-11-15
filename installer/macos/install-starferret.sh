#!/bin/bash
# StarFerret installer for Apple silicon Macs.
#
# The easy way is the StarFerret app (StarFerret.dmg), which runs this script.
# For IT people, one Terminal line, no account, no sudo:
#   curl -fsSL https://github.com/StarFerret/board-admin/releases/latest/download/install-starferret.sh | bash
#
# Or from a checkout:
#   bash installer/macos/install-starferret.sh
#
# What it does:
#   1. Checks this Mac (Apple silicon, memory, disk).
#   2. Gets the StarFerret app (skipped when run from a checkout).
#   3. Sets up a private Python with uv. Nothing is installed system wide.
#   4. Starts Board and Control as LaunchAgents, so they survive a reboot,
#      and opens Control so the admin can be made while the rest installs.
#   5. Installs Ollama if it is missing and starts it.
#   6. Installs LibreChat (chat) with its database. No Docker.
#   7. Installs n8n (automations). No Docker.
#   8. Downloads a model sized to this Mac's memory, through Control, then checks it runs on the GPU.
#   9. Opens the Board in your browser.
#
# StarFerret ships three apps and only three: LibreChat, n8n, and the Board.
#
# Written for the stock /bin/bash 3.2 that ships with macOS.
set -euo pipefail

REPO="StarFerret/board-admin"
REF="${STARFERRET_REF:-main}"
HOME_DIR="${STARFERRET_HOME:-$HOME/.starferret}"
BOARD_PORT="${PORT:-7410}"
CONTROL_PORT="${CONTROL_PORT:-7411}"
LIBRECHAT_PORT="${STARFERRET_LIBRECHAT_PORT:-3080}"
N8N_PORT="${STARFERRET_N8N_PORT:-5678}"
MONGO_PORT="${STARFERRET_MONGO_PORT:-27410}"   # not the usual 27017, so we never collide with another MongoDB
# Pinned so every customer gets a combination we have looked at. Raise them on purpose.
LIBRECHAT_VERSION="${STARFERRET_LIBRECHAT_VERSION:-v0.8.8}"
MONGO_VERSION="${STARFERRET_MONGO_VERSION:-8.0.13}"
NODE_LINE="24"          # n8n 2.x needs Node.js 24 or newer
N8N_SPEC="n8n@2"
OLLAMA_URL="http://127.0.0.1:11434"
AGENTS_DIR="$HOME/Library/LaunchAgents"
LABEL_SUPERVISOR="com.starferret.supervisor"
LABEL_BOARD="com.starferret.board"
LABEL_MONGO="com.starferret.mongodb"
LABEL_LIBRECHAT="com.starferret.librechat"
LABEL_N8N="com.starferret.n8n"
LEGACY_WEBUI="com.starferret.openwebui"   # Open WebUI left the product on 2026-11-12
SYSTEM_APPS_DIR="/Applications"
USER_APPS_DIR="$HOME/Applications"   # used when this Mac user cannot write to /Applications (a standard, non admin account)
OLLAMA_BIN_IN_APP="Contents/Resources/ollama"
SERVICE_PATH="$HOME_DIR/node/bin:$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"

DRY_RUN=0
WITH_LIBRECHAT=1
WITH_N8N=1
OPEN_BROWSER=1
UNINSTALL=0
EVERYTHING=0
MODEL="${STARFERRET_MODEL:-}"

usage() {
  cat <<'EOF'
StarFerret installer

  --dry-run         Show what would happen. Change nothing.
  --model NAME      Pull this Ollama model instead of picking one by memory.
  --no-librechat    Skip LibreChat (chat).
  --no-n8n          Skip n8n (automations).
  --no-browser      Do not open the browser at the end.
  --uninstall       Stop the services and remove their LaunchAgents. Keeps your data.
  --uninstall --everything
                    Also delete StarFerret's files and data, and the Ollama, uv,
                    and model this installer added. Things you had before stay.
  -h, --help        Show this help.

Environment:
  STARFERRET_HOME   Install location when not run from a checkout (default ~/.starferret)
  STARFERRET_REF    Branch or tag to install (default main)
  STARFERRET_BUNDLE A starferret-macos.tar.gz to install instead of downloading one
                    (the StarFerret Mac app passes the copy it carries)
  STARFERRET_GUI    Set to 1 by the Mac app: progress lines every poll, not every 30 seconds
EOF
}

while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run) DRY_RUN=1 ;;
    --model) shift; MODEL="${1:-}"; [ -n "$MODEL" ] || { echo "--model needs a name" >&2; exit 2; } ;;
    --no-librechat) WITH_LIBRECHAT=0 ;;
    --no-n8n) WITH_N8N=0 ;;
    --no-open-webui) ;;   # accepted for old instructions; Open WebUI is no longer installed
    --no-browser) OPEN_BROWSER=0 ;;
    --uninstall) UNINSTALL=1 ;;
    --everything) EVERYTHING=1 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done

if [ "$EVERYTHING" -eq 1 ] && [ "$UNINSTALL" -eq 0 ]; then
  echo "--everything only goes with --uninstall" >&2; exit 2
fi

# ---------- output ----------
if [ -t 1 ]; then
  BOLD=$(printf '\033[1m'); DIM=$(printf '\033[2m'); YELLOW=$(printf '\033[33m')
  RED=$(printf '\033[31m'); GREEN=$(printf '\033[32m'); RESET=$(printf '\033[0m')
else
  BOLD=""; DIM=""; YELLOW=""; RED=""; GREEN=""; RESET=""
fi
STEP=0
TOTAL=9
step() { STEP=$((STEP + 1)); printf '\n%s[%d/%d] %s%s\n' "$BOLD" "$STEP" "$TOTAL" "$1" "$RESET"; }
info() { printf '      %s\n' "$1"; }
ok()   { printf '      %s✓%s %s\n' "$GREEN" "$RESET" "$1"; }
warn() { printf '      %s!%s %s\n' "$YELLOW" "$RESET" "$1"; }
die()  { printf '\n%sInstall stopped.%s %s\n' "$RED" "$RESET" "$1" >&2; exit 1; }

# Run a command, or only print it under --dry-run.
run() {
  if [ "$DRY_RUN" -eq 1 ]; then
    printf '      %swould run:%s %s\n' "$DIM" "$RESET" "$*"
  else
    "$@"
  fi
}

have() { command -v "$1" >/dev/null 2>&1; }

http_ok() { curl -fsS -o /dev/null --max-time 3 "$1" 2>/dev/null; }

wait_http() { # url, seconds
  local i=0
  while [ "$i" -lt "$2" ]; do
    http_ok "$1" && return 0
    sleep 1
    i=$((i + 1))
  done
  return 1
}

port_busy() { lsof -nP -iTCP:"$1" -sTCP:LISTEN >/dev/null 2>&1; }

# Where Ollama.app already is: /Applications first, then ~/Applications. Prints the app path.
find_ollama_app() {
  local dir
  for dir in "$SYSTEM_APPS_DIR" "$USER_APPS_DIR"; do
    if [ -x "$dir/Ollama.app/$OLLAMA_BIN_IN_APP" ]; then
      printf '%s\n' "$dir/Ollama.app"
      return 0
    fi
  done
  return 1
}

# Move a downloaded Ollama.app into /Applications, or ~/Applications when that is not writable.
# Prints where it went. Never asks for a password.
place_ollama_app() { # path to the unpacked Ollama.app
  if mv "$1" "$SYSTEM_APPS_DIR/" 2>/dev/null; then
    printf '%s\n' "$SYSTEM_APPS_DIR/Ollama.app"
    return 0
  fi
  mkdir -p "$USER_APPS_DIR" 2>/dev/null && mv "$1" "$USER_APPS_DIR/" 2>/dev/null || return 1
  printf '%s\n' "$USER_APPS_DIR/Ollama.app"
}

# Check a file against a SHA256SUMS file (lines of "<hash>  <name>").
# Returns 0 when it matches, 1 when it does not, 2 when the file is not listed.
check_sha256() { # file, sums file, name in the sums file
  local want got
  want="$(awk -v n="$3" '{ f = $2; sub(/^\*/, "", f); if (f == n) { print $1; exit } }' "$2")"
  [ -n "$want" ] || return 2
  got="$(shasum -a 256 "$1" | awk '{print $1}')"
  [ "$got" = "$want" ]
}

# Check a file downloaded from the latest release against that release's SHA256SUMS.
# A mismatch stops the install. A release without the file, or without this name in it, only warns.
verify_release_file() { # file, name in SHA256SUMS
  local sums="$1.SHA256SUMS" rc=0
  if ! curl -fsSL -o "$sums" "https://github.com/$REPO/releases/latest/download/SHA256SUMS" 2>/dev/null; then
    warn "This release has no checksum file. Using $2 without the check."
    return 0
  fi
  check_sha256 "$1" "$sums" "$2" || rc=$?
  rm -f "$sums"
  case "$rc" in
    0) ok "$2 matches the release checksum" ;;
    1) die "$2 did not match the release checksum, so it was not installed. Run this again. If it keeps happening, tell us at hello@starferret.com." ;;
    *) warn "This release lists no checksum for $2. Using it without the check." ;;
  esac
}

# What this installer added itself, so --uninstall --everything removes that and
# nothing the Mac had before. One "key=value" per line.
RECORD="$HOME_DIR/installed-by-starferret"
remember() { # key value
  [ "$DRY_RUN" -eq 1 ] && return 0
  mkdir -p "$HOME_DIR"
  grep -qx "$1=$2" "$RECORD" 2>/dev/null || printf '%s=%s\n' "$1" "$2" >> "$RECORD"
}
recalled() { # key: prints every value saved under it
  [ -f "$RECORD" ] || return 0
  sed -n "s/^$1=//p" "$RECORD"
}

# ---------- launchd ----------
GUI="gui/$(id -u)"

agent_loaded() { launchctl print "$GUI/$1" >/dev/null 2>&1; }

agent_stop() {
  if agent_loaded "$1"; then
    run launchctl bootout "$GUI/$1" || true
  fi
}

agent_start() { # label
  local plist="$AGENTS_DIR/$1.plist"
  agent_stop "$1"
  # bootout returns before the job is fully gone; a short retry avoids a spurious error.
  if [ "$DRY_RUN" -eq 1 ]; then
    run launchctl bootstrap "$GUI" "$plist"
    return 0
  fi
  local i=0
  while [ "$i" -lt 5 ]; do
    launchctl bootstrap "$GUI" "$plist" 2>/dev/null && return 0
    sleep 1
    i=$((i + 1))
  done
  launchctl bootstrap "$GUI" "$plist"
}

# write_plist label workdir logname "ENV_KEY=value ..." -- program args...
write_plist() {
  local label="$1" workdir="$2" logname="$3" envs="$4"
  shift 5
  local plist="$AGENTS_DIR/$label.plist"
  if [ "$DRY_RUN" -eq 1 ]; then
    printf '      %swould write:%s %s\n' "$DIM" "$RESET" "$plist"
    return 0
  fi
  mkdir -p "$AGENTS_DIR" "$LOG_DIR"
  {
    cat <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
  <dict>
    <key>Label</key>
    <string>$label</string>
    <key>ProgramArguments</key>
    <array>
EOF
    for arg in "$@"; do printf '      <string>%s</string>\n' "$arg"; done
    cat <<EOF
    </array>
    <key>WorkingDirectory</key>
    <string>$workdir</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>$LOG_DIR/$logname.log</string>
    <key>StandardErrorPath</key>
    <string>$LOG_DIR/$logname.log</string>
    <key>EnvironmentVariables</key>
    <dict>
      <key>PATH</key>
      <string>$SERVICE_PATH</string>
EOF
    local pair
    for pair in $envs; do
      printf '      <key>%s</key>\n      <string>%s</string>\n' "${pair%%=*}" "${pair#*=}"
    done
    cat <<EOF
    </dict>
  </dict>
</plist>
EOF
  } > "$plist"
}

# ---------- uninstall ----------
# Delete a path under --uninstall --everything, never anything that is not ours.
remove_path() { # path, what to call it
  case "$1" in
    ""|"/"|"$HOME"|"$HOME/") warn "Skipped an unsafe path: '$1'"; return 0 ;;
  esac
  if [ -e "$1" ]; then
    run rm -rf "$1"
    ok "Deleted $2"
  fi
}

if [ "$UNINSTALL" -eq 1 ]; then
  printf '%sRemoving StarFerret services%s\n' "$BOLD" "$RESET"
  for label in "$LABEL_LIBRECHAT" "$LABEL_N8N" "$LABEL_MONGO" "$LABEL_BOARD" "$LABEL_SUPERVISOR" "$LEGACY_WEBUI"; do
    agent_stop "$label"
    if [ -f "$AGENTS_DIR/$label.plist" ]; then
      run rm -f "$AGENTS_DIR/$label.plist"
      ok "Removed $label"
    fi
  done
  if [ "$EVERYTHING" -eq 0 ]; then
    info "Your data and models were kept."
    info "To delete them too: run this again with --uninstall --everything."
    exit 0
  fi

  printf '\n%sDeleting StarFerret and what it added%s\n' "$BOLD" "$RESET"
  if [ "$DRY_RUN" -eq 0 ] && [ -t 1 ]; then
    warn "This deletes everyone's chats, Board workspaces, and automations on this Mac. Press Ctrl-C in the next 10 seconds to stop."
    sleep 10
  fi
  # Read the record before its folder goes.
  R_OLLAMA_APP="$(recalled ollama_app | tail -1)"
  R_OLLAMA_HOME="$(recalled ollama_models_folder | tail -1)"
  R_UV="$(recalled uv | tail -1)"
  R_MODELS="$(recalled model)"
  R_CHECKOUTS="$(recalled checkout)"

  if [ -n "$R_OLLAMA_APP" ]; then
    # Ollama came with StarFerret: quit it, then delete it and, if StarFerret made it, its model folder.
    if [ "$DRY_RUN" -eq 1 ]; then
      info "would quit Ollama"
    else
      osascript -e 'quit app "Ollama"' >/dev/null 2>&1 || true
      sleep 2
    fi
    remove_path "$R_OLLAMA_APP" "Ollama ($R_OLLAMA_APP)"
    [ -n "$R_OLLAMA_HOME" ] && remove_path "$R_OLLAMA_HOME" "the downloaded models ($R_OLLAMA_HOME)"
  elif [ -n "$R_MODELS" ]; then
    # Ollama was here before StarFerret: keep it, remove only the models StarFerret downloaded.
    OLLAMA_CMD=""
    if have ollama; then OLLAMA_CMD="$(command -v ollama)"; elif OLLAMA_APP="$(find_ollama_app)"; then OLLAMA_CMD="$OLLAMA_APP/$OLLAMA_BIN_IN_APP"; fi
    printf '%s\n' "$R_MODELS" | while IFS= read -r m; do
      [ -n "$m" ] || continue
      if [ -z "$OLLAMA_CMD" ]; then
        warn "Ollama is gone, so $m could not be removed through it."
      elif run "$OLLAMA_CMD" rm "$m" >/dev/null 2>&1; then
        ok "Removed the model $m (Ollama was here before StarFerret, so it stays)"
      else
        warn "Could not remove $m. Open Ollama and run: ollama rm $m"
      fi
    done
  fi

  if [ -n "$R_UV" ]; then
    remove_path "$R_UV" "uv"
    remove_path "${R_UV%/uv}/uvx" "uvx"
    remove_path "$HOME/.local/share/uv" "uv's Python"
  fi

  remove_path "$HOME_DIR" "StarFerret's programs, data, and logs ($HOME_DIR)"
  printf '%s\n' "$R_CHECKOUTS" | while IFS= read -r c; do
    [ -n "$c" ] || continue
    info "This Mac also ran StarFerret from $c. Its data folder was kept. Delete that folder yourself if you no longer want it."
  done
  if [ -d "/Applications/StarFerret.app" ] || [ -d "$HOME/Applications/StarFerret.app" ]; then
    info "The StarFerret app is still in Applications. Drag it to the Trash to finish."
  fi
  if [ "$DRY_RUN" -eq 1 ]; then
    printf '\n%sDry run finished. Nothing was changed.%s\n' "$YELLOW" "$RESET"
  else
    printf '\n%sStarFerret is removed from this Mac.%s\n' "$BOLD" "$RESET"
  fi
  exit 0
fi

printf '%sStarFerret%s  local AI on your own Mac\n' "$BOLD" "$RESET"
[ "$DRY_RUN" -eq 1 ] && printf '%sDry run. Nothing will be changed.%s\n' "$YELLOW" "$RESET"

# ---------- 1. check this Mac ----------
step "Checking this Mac"
[ "$(uname -s)" = "Darwin" ] || die "StarFerret runs on macOS. This is $(uname -s)."
[ "$(uname -m)" = "arm64" ] || die "StarFerret needs an Apple silicon Mac (M1 or newer). This Mac is $(uname -m)."
# Under Rosetta everything installs as Intel code, and Intel code cannot use the GPU (Metal).
if [ "$(sysctl -n sysctl.proc_translated 2>/dev/null || echo 0)" = "1" ]; then
  die "This Terminal is running under Rosetta. Quit it, open Terminal normally (Get Info, untick 'Open using Rosetta'), and run this again."
fi
have curl || die "curl is missing."

RAM_GB=$(( ($(sysctl -n hw.memsize) + 536870912) / 1073741824 ))
FREE_GB=$(df -g "$HOME" | awk 'NR==2 {print $4}')
CHIP=$(sysctl -n machdep.cpu.brand_string 2>/dev/null || echo "Apple silicon")
ok "$CHIP, ${RAM_GB}GB memory, ${FREE_GB}GB free disk"

# Pick the largest model from the Board failover ladder that leaves room to work.
if [ -z "$MODEL" ]; then
  if [ "$RAM_GB" -ge 48 ]; then
    MODEL="qwen3.8:27b"
  elif [ "$RAM_GB" -ge 24 ]; then
    MODEL="gemma4:latest"
  else
    MODEL="gemma4:12b-mlx"
  fi
  info "Model for ${RAM_GB}GB of memory: $MODEL"
else
  info "Model (your choice): $MODEL"
fi
[ "$RAM_GB" -ge 16 ] || warn "This Mac has ${RAM_GB}GB of memory. The smallest model wants 16GB, so answers will be slow or may not load."
[ "$FREE_GB" -ge 30 ] || warn "Under 30GB of free disk. The model, LibreChat, and n8n may not fit."

# ---------- 2. get the app ----------
step "Getting StarFerret"
SCRIPT_PATH="${BASH_SOURCE[0]:-}"
APP_DIR=""
if [ -n "$SCRIPT_PATH" ] && [ -f "$SCRIPT_PATH" ]; then
  CANDIDATE="$(cd "$(dirname "$SCRIPT_PATH")/../.." && pwd)"
  if [ -f "$CANDIDATE/server/app.py" ] && [ -f "$CANDIDATE/supervisor/app.py" ]; then
    APP_DIR="$CANDIDATE"
    ok "Using this checkout: $APP_DIR"
    remember checkout "$APP_DIR"
  fi
fi

if [ -z "$APP_DIR" ]; then
  APP_DIR="$HOME_DIR/app"
  RELEASE_URL="https://github.com/$REPO/releases/latest/download/starferret-macos.tar.gz"
  SOURCE_URL="https://github.com/$REPO/archive/refs/heads/$REF.tar.gz"
  BUNDLE="${STARFERRET_BUNDLE:-}"
  if [ -n "$BUNDLE" ] && [ ! -f "$BUNDLE" ]; then
    die "The StarFerret copy at $BUNDLE is missing. Download StarFerret again."
  fi
  if [ "$DRY_RUN" -eq 1 ]; then
    if [ -n "$BUNDLE" ]; then
      info "would unpack $BUNDLE into $APP_DIR (your data folder is kept)"
    else
      info "would download the latest release into $APP_DIR (your data folder is kept)"
    fi
  else
    TMP="$(mktemp -d)"
    trap 'rm -rf "$TMP"' EXIT
    # Release bundles ship with the web UI already built. Source archives do not.
    if [ -n "$BUNDLE" ]; then
      # The Mac app carries its own copy. The app is signed, so no checksum is needed.
      cp "$BUNDLE" "$TMP/app.tar.gz"
      info "Using the StarFerret copy inside the app"
    elif [ "$REF" = "main" ] && curl -fsSL -o "$TMP/app.tar.gz" "$RELEASE_URL" 2>/dev/null; then
      info "Downloaded the latest release"
      verify_release_file "$TMP/app.tar.gz" "starferret-macos.tar.gz"
    else
      curl -fsSL -o "$TMP/app.tar.gz" "$SOURCE_URL" || die "Could not download StarFerret from GitHub. Check your connection."
      info "Downloaded source ($REF)"
    fi
    mkdir -p "$APP_DIR"
    # data/ is never in the archive, so an upgrade leaves it alone.
    tar -xzf "$TMP/app.tar.gz" -C "$APP_DIR" --strip-components=1
    ok "Installed to $APP_DIR"
  fi
fi
# An installed copy keeps the program, the data, and Python in separate folders,
# so an update can replace the program folder whole and never touch the data.
if [ "$APP_DIR" = "$HOME_DIR/app" ]; then
  DATA_DIR="$HOME_DIR/data"
  VENV_DIR="$HOME_DIR/venv"
  LOG_DIR="$HOME_DIR/logs"
  if [ -d "$APP_DIR/data" ] && [ ! -d "$DATA_DIR" ]; then
    run mv "$APP_DIR/data" "$DATA_DIR"   # layout used before 2026-11
  fi
else
  DATA_DIR="$APP_DIR/data"
  VENV_DIR="$APP_DIR/.venv"
  LOG_DIR="$APP_DIR/data/stack"
fi

if [ "$DRY_RUN" -eq 0 ] && [ ! -f "$APP_DIR/web/dist/index.html" ]; then
  if have npm; then
    info "Building the Board UI (first run only)"
    (cd "$APP_DIR/web" && npm install --no-fund --no-audit --loglevel=error && npm run build >/dev/null) \
      || die "The Board UI build failed. Run 'npm install && npm run build' in $APP_DIR/web to see why."
    ok "Board UI built"
  else
    die "This copy has no built Board UI and Node.js is not installed. Install the release bundle, or install Node.js and run again."
  fi
fi

if [ "$DRY_RUN" -eq 0 ] && [ ! -f "$APP_DIR/control-web/dist/index.html" ]; then
  if have npm; then
    info "Building the Control UI (first run only)"
    (cd "$APP_DIR/control-web" && npm install --no-fund --no-audit --loglevel=error && npm run build >/dev/null) \
      || die "The Control UI build failed. Run 'npm install && npm run build' in $APP_DIR/control-web to see why."
    ok "Control UI built"
  else
    die "This copy has no built Control UI and Node.js is not installed. Install the release bundle, or install Node.js and run again."
  fi
fi

# ---------- 3. private Python ----------
step "Setting up a private Python"
UV=""
if have uv; then UV="$(command -v uv)"; elif [ -x "$HOME/.local/bin/uv" ]; then UV="$HOME/.local/bin/uv"; fi
if [ -z "$UV" ]; then
  info "Installing uv (manages Python without touching the system one)"
  if [ "$DRY_RUN" -eq 1 ]; then
    info "would run: curl -LsSf https://astral.sh/uv/install.sh | sh"
    UV="$HOME/.local/bin/uv"
  else
    curl -LsSf https://astral.sh/uv/install.sh | env UV_NO_MODIFY_PATH=1 sh >/dev/null 2>&1 \
      || die "Could not install uv. See https://docs.astral.sh/uv/ and run again."
    UV="$HOME/.local/bin/uv"
    [ -x "$UV" ] || die "uv installed but was not found at $UV."
    remember uv "$UV"
  fi
fi
PY="$VENV_DIR/bin/python"
if [ -x "$PY" ]; then
  ok "Using the existing environment"
else
  run "$UV" venv --quiet --python 3.12 "$VENV_DIR"
fi
run "$UV" pip install --quiet --python "$PY" -r "$APP_DIR/server/requirements.txt"
ok "Python ready"

# ---------- 4. Board and Control ----------
# They start before the slow parts, so the person can make the Control admin and
# watch the rest from the browser instead of waiting on this window.
step "Starting Board and Control"
agent_stop "$LABEL_BOARD"
agent_stop "$LABEL_SUPERVISOR"
[ "$DRY_RUN" -eq 1 ] || sleep 1

for p in "$BOARD_PORT" "$CONTROL_PORT"; do
  if port_busy "$p"; then
    if [ "$DRY_RUN" -eq 1 ]; then
      warn "Port $p is in use. A real install would stop here until it is free."
    else
      die "Port $p is already in use by another program. Stop it (lsof -nP -iTCP:$p -sTCP:LISTEN shows which) and run again."
    fi
  fi
done

SERVICE_ENV="PORT=$BOARD_PORT CONTROL_PORT=$CONTROL_PORT OLLAMA_MODEL=$MODEL STARFERRET_DATA_DIR=$DATA_DIR STARFERRET_HOME=$HOME_DIR"
write_plist "$LABEL_SUPERVISOR" "$APP_DIR" "supervisor" "$SERVICE_ENV" -- "$PY" -m supervisor
write_plist "$LABEL_BOARD" "$APP_DIR" "board" "$SERVICE_ENV" -- "$PY" -m server
agent_start "$LABEL_SUPERVISOR"
agent_start "$LABEL_BOARD"

if [ "$DRY_RUN" -eq 0 ]; then
  wait_http "http://127.0.0.1:$BOARD_PORT/api/settings/host" 40 \
    || die "The Board did not start. See $LOG_DIR/board.log."
  wait_http "http://127.0.0.1:$CONTROL_PORT/api/control/health" 20 \
    || warn "Control did not answer yet. See $LOG_DIR/supervisor.log."
  ok "Board and Control are running, and will start again after a reboot"
fi
CONTROL_URL="http://127.0.0.1:$CONTROL_PORT/models"
if [ "$OPEN_BROWSER" -eq 1 ]; then
  if [ "$DRY_RUN" -eq 1 ]; then
    info "would open Control at $CONTROL_URL"
  else
    open "$CONTROL_URL" || true
    info "Control is open in your browser. Create your admin there while the rest installs."
  fi
fi

# ---------- 5. Ollama ----------
step "Installing the model runtime"
OLLAMA=""
OLLAMA_APP="$(find_ollama_app || true)"
if have ollama; then OLLAMA="$(command -v ollama)"; elif [ -n "$OLLAMA_APP" ]; then OLLAMA="$OLLAMA_APP/$OLLAMA_BIN_IN_APP"; fi
if [ -z "$OLLAMA" ]; then
  info "Downloading Ollama"
  if [ "$DRY_RUN" -eq 1 ]; then
    info "would download Ollama and put it in $SYSTEM_APPS_DIR (or $USER_APPS_DIR if that is not writable)"
    OLLAMA_APP="$SYSTEM_APPS_DIR/Ollama.app"
    OLLAMA="$OLLAMA_APP/$OLLAMA_BIN_IN_APP"
  else
    OTMP="$(mktemp -d)"
    # A model folder that is not there yet will hold only what StarFerret downloads.
    [ -d "$HOME/.ollama" ] || remember ollama_models_folder "$HOME/.ollama"
    curl -fL --progress-bar -o "$OTMP/Ollama.zip" "https://ollama.com/download/Ollama-darwin.zip" \
      || die "Could not download Ollama. Install it from https://ollama.com/download and run again."
    unzip -q "$OTMP/Ollama.zip" -d "$OTMP"
    OLLAMA_APP="$(place_ollama_app "$OTMP/Ollama.app")" \
      || die "Could not put Ollama in Applications. Drag Ollama.app from $OTMP into Applications yourself and run again."
    rm -rf "$OTMP"
    remember ollama_app "$OLLAMA_APP"
    OLLAMA="$OLLAMA_APP/$OLLAMA_BIN_IN_APP"
    ok "Ollama installed in ${OLLAMA_APP%/Ollama.app}"
  fi
else
  ok "Ollama already installed"
fi

if http_ok "$OLLAMA_URL/api/tags"; then
  ok "Ollama is running"
elif [ "$DRY_RUN" -eq 1 ]; then
  info "would start Ollama"
else
  if [ -n "$OLLAMA_APP" ] && [ -d "$OLLAMA_APP" ]; then
    open "$OLLAMA_APP" --args hidden
  else
    nohup "$OLLAMA" serve >/dev/null 2>&1 &
  fi
  wait_http "$OLLAMA_URL/api/tags" 45 || die "Ollama did not start. Open the Ollama app once, then run this again."
  ok "Ollama started"
fi

# ---------- 6. LibreChat ----------
# LibreChat and n8n are Node.js apps. Both run directly on the Mac: no Docker.
# They live under $HOME_DIR even when StarFerret itself runs from a checkout.
NODE_DIR="$HOME_DIR/node"
NODE="$NODE_DIR/bin/node"
NPM="$NODE_DIR/bin/npm"
HOST_NAME="$(scutil --get LocalHostName 2>/dev/null || hostname -s).local"   # stays the same when the IP changes

ensure_node() {
  if [ -x "$NODE" ]; then return 0; fi
  if [ "$DRY_RUN" -eq 1 ]; then
    info "would download a private Node.js $NODE_LINE into $NODE_DIR"
    return 0
  fi
  info "Downloading a private Node.js (it does not touch any Node.js you already have)"
  local sums file sum tmp
  sums="$(curl -fsSL "https://nodejs.org/dist/latest-v$NODE_LINE.x/SHASUMS256.txt")" \
    || die "Could not reach nodejs.org. Check your connection and run again."
  file="$(printf '%s\n' "$sums" | awk '/darwin-arm64\.tar\.gz$/ {print $2}')"
  sum="$(printf '%s\n' "$sums" | awk '/darwin-arm64\.tar\.gz$/ {print $1}')"
  [ -n "$file" ] || die "Could not find a Node.js build for this Mac."
  tmp="$(mktemp -d)"
  curl -fL --progress-bar -o "$tmp/node.tar.gz" "https://nodejs.org/dist/latest-v$NODE_LINE.x/$file" \
    || die "The Node.js download failed. Run again."
  [ "$(shasum -a 256 "$tmp/node.tar.gz" | awk '{print $1}')" = "$sum" ] \
    || die "The Node.js download did not match its checksum. Run again."
  mkdir -p "$NODE_DIR"
  tar -xzf "$tmp/node.tar.gz" -C "$NODE_DIR" --strip-components=1
  rm -rf "$tmp"
  ok "Node.js ready"
}

# Run npm with the private Node.js first in PATH.
npm_run() { env PATH="$NODE_DIR/bin:$PATH" "$NPM" "$@"; }

# Remove Open WebUI's service if an older install left one. Its data folder is kept.
agent_stop "$LEGACY_WEBUI"
if [ -f "$AGENTS_DIR/$LEGACY_WEBUI.plist" ]; then run rm -f "$AGENTS_DIR/$LEGACY_WEBUI.plist"; fi

step "Installing LibreChat (chat)"
LIBRECHAT_STATE="skipped"
if [ "$WITH_LIBRECHAT" -eq 0 ]; then
  info "Skipped (--no-librechat)"
else
  agent_stop "$LABEL_LIBRECHAT"
  [ "$DRY_RUN" -eq 1 ] || sleep 1
  if port_busy "$LIBRECHAT_PORT"; then
    warn "Port $LIBRECHAT_PORT is already in use, so something is serving there. Leaving it alone."
    LIBRECHAT_STATE="existing"
  else
    ensure_node
    MONGO_DIR="$HOME_DIR/mongodb"
    LC_DIR="$HOME_DIR/librechat"
    LC_DATA="$DATA_DIR/librechat"

    # LibreChat keeps accounts and chats in MongoDB. It listens on this Mac only.
    if [ -x "$MONGO_DIR/bin/mongod" ]; then
      ok "Database already installed"
    elif [ "$DRY_RUN" -eq 1 ]; then
      info "would download MongoDB $MONGO_VERSION into $MONGO_DIR"
    else
      info "Downloading the database LibreChat uses"
      MTMP="$(mktemp -d)"
      curl -fL --progress-bar -o "$MTMP/mongo.tgz" "https://fastdl.mongodb.org/osx/mongodb-macos-arm64-$MONGO_VERSION.tgz" \
        || die "The database download failed. Run again, or use --no-librechat to skip chat."
      mkdir -p "$MONGO_DIR"
      tar -xzf "$MTMP/mongo.tgz" -C "$MONGO_DIR" --strip-components=1
      rm -rf "$MTMP"
    fi
    run mkdir -p "$DATA_DIR/mongodb" "$LC_DATA"
    write_plist "$LABEL_MONGO" "$MONGO_DIR" "mongodb" "" \
      -- "$MONGO_DIR/bin/mongod" --dbpath "$DATA_DIR/mongodb" --bind_ip 127.0.0.1 --port "$MONGO_PORT"
    agent_start "$LABEL_MONGO"

    if [ -f "$LC_DIR/.starferret-version" ] && [ "$(cat "$LC_DIR/.starferret-version")" = "$LIBRECHAT_VERSION" ]; then
      ok "LibreChat $LIBRECHAT_VERSION already installed"
    elif [ "$DRY_RUN" -eq 1 ]; then
      info "would download LibreChat $LIBRECHAT_VERSION ready built from the StarFerret release into $LC_DIR,"
      info "or, if the release has none for this version, build it from source (about ten minutes)"
    else
      LTMP="$(mktemp -d)"
      LC_ASSET="librechat-$LIBRECHAT_VERSION-darwin-arm64.tar.gz"
      rm -rf "$LC_DIR.new"
      mkdir -p "$LC_DIR.new"
      # Releases built by CI carry LibreChat already built for Apple silicon and Node.js 24.
      # Ask first (quietly) whether the release has it, so the real download can show progress.
      LC_URL="https://github.com/$REPO/releases/latest/download/$LC_ASSET"
      if curl -fsIL -o /dev/null --max-time 20 "$LC_URL" 2>/dev/null; then
        info "Downloading LibreChat $LIBRECHAT_VERSION, ready built"
        curl -fL --progress-bar -o "$LTMP/$LC_ASSET" "$LC_URL" \
          || die "The LibreChat download failed. Run again, or use --no-librechat to skip chat."
        verify_release_file "$LTMP/$LC_ASSET" "$LC_ASSET"
        tar -xzf "$LTMP/$LC_ASSET" -C "$LC_DIR.new" --strip-components=1
        ok "LibreChat $LIBRECHAT_VERSION unpacked, ready built"
      else
        info "No ready built LibreChat $LIBRECHAT_VERSION in the release. Building it here instead."
        curl -fsSL -o "$LTMP/librechat.tar.gz" "https://github.com/danny-avila/LibreChat/archive/refs/tags/$LIBRECHAT_VERSION.tar.gz" \
          || die "The LibreChat download failed. Run again, or use --no-librechat to skip chat."
        tar -xzf "$LTMP/librechat.tar.gz" -C "$LC_DIR.new" --strip-components=1
        info "Building LibreChat. This is the second slow part, about ten minutes."
        (cd "$LC_DIR.new" && npm_run ci --no-audit --no-fund --loglevel=error >"$LOG_DIR/librechat-build.log" 2>&1 \
          && npm_run run frontend >>"$LOG_DIR/librechat-build.log" 2>&1) \
          || die "LibreChat did not build. See $LOG_DIR/librechat-build.log, or use --no-librechat to skip chat."
      fi
      rm -rf "$LTMP"
      # Keep people's uploaded files across a LibreChat upgrade.
      if [ -d "$LC_DIR/uploads" ]; then cp -R "$LC_DIR/uploads" "$LC_DIR.new/uploads"; fi
      rm -rf "$LC_DIR"
      mv "$LC_DIR.new" "$LC_DIR"
      printf '%s\n' "$LIBRECHAT_VERSION" > "$LC_DIR/.starferret-version"
      ok "LibreChat $LIBRECHAT_VERSION installed"
    fi

    if [ "$DRY_RUN" -eq 1 ]; then
      info "would write LibreChat settings pointing at the local model $MODEL"
    else
      # Secrets are made once and kept in the data folder, so an upgrade does not sign everyone out.
      if [ ! -f "$LC_DATA/secrets.env" ]; then
        {
          printf 'JWT_SECRET=%s\n' "$(openssl rand -hex 32)"
          printf 'JWT_REFRESH_SECRET=%s\n' "$(openssl rand -hex 32)"
          printf 'CREDS_KEY=%s\n' "$(openssl rand -hex 32)"
          printf 'CREDS_IV=%s\n' "$(openssl rand -hex 16)"
        } > "$LC_DATA/secrets.env"
        chmod 600 "$LC_DATA/secrets.env"
      fi
      cat > "$LC_DATA/librechat.yaml" <<YAML
# Written by the StarFerret installer. Points LibreChat at the models on this Mac.
version: 1.2.1
cache: true
endpoints:
  custom:
    - name: "Local"
      apiKey: "ollama"
      baseURL: "$OLLAMA_URL/v1/"
      models:
        default: ["$MODEL"]
        fetch: true
      titleConvo: true
      titleModel: "current_model"
      modelDisplayLabel: "Local"
YAML
      {
        cat "$LC_DATA/secrets.env"
        cat <<ENV
HOST=0.0.0.0
PORT=$LIBRECHAT_PORT
MONGO_URI=mongodb://127.0.0.1:$MONGO_PORT/LibreChat
DOMAIN_CLIENT=http://$HOST_NAME:$LIBRECHAT_PORT
DOMAIN_SERVER=http://$HOST_NAME:$LIBRECHAT_PORT
CONFIG_PATH=$LC_DATA/librechat.yaml
ENDPOINTS=custom
ALLOW_REGISTRATION=true
NO_INDEX=true
SEARCH=false
# The office network is plain http. Without this, browsers drop the sign in cookie.
SESSION_COOKIE_SECURE=false
ENV
      } > "$LC_DIR/.env"
      chmod 600 "$LC_DIR/.env"
    fi
    write_plist "$LABEL_LIBRECHAT" "$LC_DIR" "librechat" "NODE_ENV=production" \
      -- "$NODE" api/server/index.js
    agent_start "$LABEL_LIBRECHAT"
    if [ "$DRY_RUN" -eq 0 ]; then
      if wait_http "http://127.0.0.1:$LIBRECHAT_PORT/" 120; then
        ok "LibreChat is running"
        LIBRECHAT_STATE="running"
      else
        warn "LibreChat is still starting. Give it a minute. Log: $LOG_DIR/librechat.log"
        LIBRECHAT_STATE="starting"
      fi
    fi
  fi
fi

# ---------- 7. n8n ----------
step "Installing n8n (automations)"
N8N_STATE="skipped"
if [ "$WITH_N8N" -eq 0 ]; then
  info "Skipped (--no-n8n)"
else
  agent_stop "$LABEL_N8N"
  [ "$DRY_RUN" -eq 1 ] || sleep 1
  if port_busy "$N8N_PORT"; then
    warn "Port $N8N_PORT is already in use, so something is serving there. Leaving it alone."
    N8N_STATE="existing"
  else
    ensure_node
    N8N_DIR="$HOME_DIR/n8n"
    if [ -x "$N8N_DIR/bin/n8n" ]; then
      ok "n8n already installed"
    elif [ "$DRY_RUN" -eq 1 ]; then
      info "would install $N8N_SPEC into $N8N_DIR"
    else
      info "Installing n8n. A few minutes the first time."
      npm_run install --global --prefix "$N8N_DIR" --no-audit --no-fund --loglevel=error "$N8N_SPEC" >"$LOG_DIR/n8n-install.log" 2>&1 \
        || die "n8n did not install. See $LOG_DIR/n8n-install.log, or use --no-n8n to skip automations."
    fi
    run mkdir -p "$DATA_DIR/n8n"
    write_plist "$LABEL_N8N" "$DATA_DIR/n8n" "n8n" \
      "N8N_PORT=$N8N_PORT N8N_LISTEN_ADDRESS=0.0.0.0 N8N_USER_FOLDER=$DATA_DIR/n8n N8N_SECURE_COOKIE=false N8N_DIAGNOSTICS_ENABLED=false WEBHOOK_URL=http://$HOST_NAME:$N8N_PORT/" \
      -- "$N8N_DIR/bin/n8n" start
    agent_start "$LABEL_N8N"
    if [ "$DRY_RUN" -eq 0 ]; then
      if wait_http "http://127.0.0.1:$N8N_PORT/healthz" 120; then
        ok "n8n is running"
        N8N_STATE="running"
      else
        warn "n8n is still starting. Give it a minute. Log: $LOG_DIR/n8n.log"
        N8N_STATE="starting"
      fi
    fi
  fi
fi

# ---------- 8. model ----------
# Last, because it is the longest wait. Control does the download, so it keeps
# going if this window is closed, and the Models page shows the progress.
step "Downloading a model that fits your memory"
CONTROL_API="http://127.0.0.1:$CONTROL_PORT/api/control"
LOCAL_KEY=""
if [ -f "$DATA_DIR/control/local-key" ]; then
  LOCAL_KEY="$(tr -d '[:space:]' < "$DATA_DIR/control/local-key" 2>/dev/null || true)"
fi

# Print "state percent completed total error" for $MODEL from Control's download list.
pull_state() {
  curl -fsS --max-time 5 -H "X-StarFerret-Local-Key: $LOCAL_KEY" "$CONTROL_API/models/pulls" 2>/dev/null \
    | "$PY" -c '
import json, sys
name = sys.argv[1]
try:
    pulls = json.load(sys.stdin).get("pulls") or []
except ValueError:
    pulls = []
for p in pulls:
    if p.get("name") == name:
        err = (p.get("error") or "").replace("\n", " ")
        print(p.get("state"), p.get("percent") or 0, p.get("completed") or 0, p.get("total") or 0, err)
        break
else:
    print("missing 0 0 0")
' "$MODEL"
}

gb() { awk -v b="$1" 'BEGIN { printf "%.1f", b / 1073741824 }'; }

if curl -fsS --max-time 5 "$OLLAMA_URL/api/tags" 2>/dev/null | grep -q "\"name\":\"$MODEL\""; then
  ok "$MODEL is already here"
elif [ "$DRY_RUN" -eq 1 ]; then
  info "would ask Control to download $MODEL and show the progress here and on Control's Models page"
elif [ -n "$LOCAL_KEY" ] && curl -fsS -o /dev/null --max-time 10 -X POST \
    -H 'Content-Type: application/json' -H "X-StarFerret-Local-Key: $LOCAL_KEY" \
    -d "{\"name\":\"$MODEL\"}" "$CONTROL_API/models/pull" 2>/dev/null; then
  remember model "$MODEL"
  info "Downloading $MODEL. This is the slow part."
  info "You can close this window. The download keeps going, and Control shows it under Models."
  QUIET=0
  LAST_LOG=0
  while :; do
    sleep 2
    set -f   # split the reply into words without expanding any * in an error message
    set -- $(pull_state)
    set +f
    P_STATE="${1:-}"; P_PCT="${2:-0}"; P_DONE="${3:-0}"; P_TOTAL="${4:-0}"
    case "$P_STATE" in
      done)
        [ -t 1 ] && printf '\r\033[K'
        ok "$MODEL ready"
        break ;;
      failed)
        [ -t 1 ] && printf '\r\033[K'
        shift 4 2>/dev/null || set --
        P_WHY="${*:-no reason given}"
        die "The model download stopped: ${P_WHY%.}. Run this again to retry. A download that was cut off picks up where it stopped."
        ;;
      running)
        QUIET=0
        if [ "$P_TOTAL" -gt 0 ]; then LINE="$P_PCT% ($(gb "$P_DONE") of $(gb "$P_TOTAL") GB)"; else LINE="starting"; fi
        if [ -t 1 ]; then
          printf '\r\033[K      Downloading %s: %s' "$MODEL" "$LINE"
        elif [ "${STARFERRET_GUI:-0}" = "1" ] || [ $(( $(date +%s) - LAST_LOG )) -ge 30 ]; then
          info "Downloading $MODEL: $LINE"
          LAST_LOG=$(date +%s)
        fi
        ;;
      *)
        # Control did not answer, or forgot the download (it restarted). Give it a minute.
        QUIET=$((QUIET + 1))
        if [ "$QUIET" -ge 30 ]; then
          [ -t 1 ] && printf '\r\033[K'
          die "Control stopped reporting the download. Open Control, go to Models, and pull $MODEL again. It picks up where it stopped."
        fi
        ;;
    esac
  done
else
  # Control could not take the download (an older Control, or it is not answering): do it here.
  warn "Control did not take the download, so it runs in this window instead."
  remember model "$MODEL"
  info "Downloading $MODEL. This is the slow part."
  "$OLLAMA" pull "$MODEL" || die "Could not pull $MODEL. Run '$OLLAMA pull $MODEL' to see why."
  ok "$MODEL ready"
fi

# Make sure the model really sits on the GPU (Metal), not the processor.
# Loading it now also means the first real question is answered quickly.
if [ "$DRY_RUN" -eq 1 ]; then
  info "Would load $MODEL once and confirm it runs on the GPU (Metal)"
else
  if file "$OLLAMA" 2>/dev/null | grep -q "x86_64" && ! file "$OLLAMA" 2>/dev/null | grep -q "arm64"; then
    warn "The Ollama on this Mac is the Intel build, which cannot use the GPU. Remove it and run this again."
  fi
  info "Loading $MODEL to check the GPU. This can take a minute."
  curl -fsS --max-time 300 "$OLLAMA_URL/api/generate" \
    -d "{\"model\":\"$MODEL\",\"prompt\":\"hi\",\"stream\":false,\"options\":{\"num_predict\":1}}" >/dev/null 2>&1 || true
  PS_JSON="$(curl -fsS --max-time 5 "$OLLAMA_URL/api/ps" 2>/dev/null || true)"
  M_SIZE="$(printf '%s' "$PS_JSON" | sed -n 's/.*"size":\([0-9][0-9]*\).*/\1/p' | head -1)"
  M_VRAM="$(printf '%s' "$PS_JSON" | sed -n 's/.*"size_vram":\([0-9][0-9]*\).*/\1/p' | head -1)"
  if [ -n "$M_SIZE" ] && [ -n "$M_VRAM" ] && [ "$M_SIZE" -gt 0 ]; then
    GPU_PCT=$(( M_VRAM * 100 / M_SIZE ))
    if [ "$GPU_PCT" -ge 100 ]; then
      ok "$MODEL is running fully on the GPU (Metal)"
    else
      warn "$MODEL is only ${GPU_PCT}% on the GPU. It will be slow. Run again with --model and a smaller model."
    fi
  else
    warn "Could not confirm GPU use yet. Control shows it under Overview once the first message is sent."
  fi
fi

# Save the model choice so the Board uses it straight away. It has to exist first.
if [ "$DRY_RUN" -eq 0 ]; then
  curl -fsS -o /dev/null --max-time 10 -X POST -H 'Content-Type: application/json' \
    -d "{\"model\":\"$MODEL\"}" "http://127.0.0.1:$BOARD_PORT/api/settings/ollama" 2>/dev/null \
    || warn "Could not save the default model. Pick it in the Board model menu."
fi

# ---------- 9. done ----------
step "Opening the Board"
LAN_IP="$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null || true)"
BOARD_URL="http://127.0.0.1:$BOARD_PORT"
# Control makes this file until its first admin exists. It lets that admin be created from another machine.
SETUP_TOKEN=""
if [ -f "$DATA_DIR/control/setup-token" ]; then
  SETUP_TOKEN="$(tr -d '[:space:]' < "$DATA_DIR/control/setup-token" 2>/dev/null || true)"
fi

if [ "$DRY_RUN" -eq 1 ]; then
  info "would open $BOARD_URL"
  printf '\n%sDry run finished. Nothing was changed.%s\n' "$YELLOW" "$RESET"
  exit 0
fi

printf '\n%sYour Mac is now a private AI server.%s\n\n' "$BOLD" "$RESET"
printf '  Board               %s\n' "$BOARD_URL"
printf '  Control             http://127.0.0.1:%s\n' "$CONTROL_PORT"
case "$LIBRECHAT_STATE" in
  running|starting|existing) printf '  LibreChat (chat)    http://127.0.0.1:%s\n' "$LIBRECHAT_PORT" ;;
esac
case "$N8N_STATE" in
  running|starting|existing) printf '  n8n (automations)   http://127.0.0.1:%s\n' "$N8N_PORT" ;;
esac
printf '  Model               %s\n' "$MODEL"
if [ -n "$SETUP_TOKEN" ]; then
  printf '\n  Create the Control admin (keep this link to yourself, it works once):\n'
  printf '    http://%s:%s/?setup=%s\n' "${LAN_IP:-127.0.0.1}" "$CONTROL_PORT" "$SETUP_TOKEN"
fi
if [ -n "$LAN_IP" ]; then
  printf '\n  Share with your team on this network:\n'
  printf '    http://%s:%s\n' "$LAN_IP" "$BOARD_PORT"
  case "$LIBRECHAT_STATE" in
    running|starting|existing) printf '    http://%s:%s   chat\n' "$LAN_IP" "$LIBRECHAT_PORT" ;;
  esac
  case "$N8N_STATE" in
    running|starting|existing) printf '    http://%s:%s   automations\n' "$LAN_IP" "$N8N_PORT" ;;
  esac
fi
printf '\n  Start, stop, and check all three apps in Control, under Apps.\n'
printf '  Logs: %s\n' "$LOG_DIR"
printf '  Remove the services: bash %s/installer/macos/install-starferret.sh --uninstall\n' "$APP_DIR"
printf '  Remove everything:   bash %s/installer/macos/install-starferret.sh --uninstall --everything\n' "$APP_DIR"
printf '\n  Want the whole package: preloaded Macs, software, and support? hello@starferret.com\n\n'

if [ "$OPEN_BROWSER" -eq 1 ]; then open "$BOARD_URL" || true; fi
