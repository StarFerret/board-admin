#!/bin/bash
# Stand-in for install-starferret.sh, for looking at the Mac app without installing anything.
# Prints the same kinds of lines with pauses, then exits. FAKE_FAIL=1 ends with a failure.
#   STARFERRET_INSTALL_SCRIPT=$PWD/installer/macos/app/fake-install.sh STARFERRET_AUTOSTART=1 <app>/Contents/MacOS/StarFerret
echo "StarFerret  local AI on your own Mac"
echo "bundle passed: ${STARFERRET_BUNDLE:-none} gui=${STARFERRET_GUI:-0}"
titles=("Checking this Mac" "Getting StarFerret" "Setting up a private Python" "Starting Board and Control" "Installing the model runtime" "Installing LibreChat (chat)" "Installing n8n (automations)" "Downloading a model that fits your memory" "Opening the Board")
i=1
for t in "${titles[@]}"; do
  printf '\n[%d/9] %s\n' "$i" "$t"
  if [ "$i" -eq 8 ]; then
    for p in 0 12 27 41 58 73 88 99; do
      printf '      Downloading qwen3.8:27b: %d%% (%s of 17.0 GB)\n' "$p" "$(awk -v p=$p 'BEGIN{printf "%.1f", 17*p/100}')"
      sleep 1.5
    done
    echo "      ✓ qwen3.8:27b ready"
  else
    sleep 1
    echo "      ✓ $t done"
  fi
  i=$((i+1))
done
[ "${FAKE_FAIL:-0}" = "1" ] && { printf '\nInstall stopped. Port 7410 is already in use by another program. Stop it and run again.\n' >&2; exit 1; }
exit 0
