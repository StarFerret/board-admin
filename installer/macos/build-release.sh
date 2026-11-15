#!/bin/bash
# Build the release bundle the installer downloads: source plus a built web UI.
# The release workflow (.github/workflows/release.yml) runs this on every v* tag and
# uploads everything in dist/. By hand:
#   gh release create v0.1.0 dist/*
set -euo pipefail

# Usage: build-release.sh [version]. Without one, the version is the date and commit.
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
VERSION="${1:-$(date +%Y.%m.%d)-$(git -C "$ROOT" rev-parse --short HEAD 2>/dev/null || echo local)}"
OUT="$ROOT/dist"
STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT

(cd "$ROOT/web" && npm install --no-fund --no-audit --loglevel=error && npm run build)
(cd "$ROOT/control-web" && npm install --no-fund --no-audit --loglevel=error && npm run build)

mkdir -p "$STAGE/starferret/web" "$STAGE/starferret/control-web" "$OUT"
for item in server supervisor catalog stacks installer README.md DOCS.md; do
  cp -R "$ROOT/$item" "$STAGE/starferret/"
done
cp -R "$ROOT/web/dist" "$STAGE/starferret/web/dist"
cp -R "$ROOT/control-web/dist" "$STAGE/starferret/control-web/dist"
printf '%s\n' "$VERSION" > "$STAGE/starferret/VERSION"   # Control → Updates reads this
find "$STAGE" -name "__pycache__" -type d -prune -exec rm -rf {} +

tar -czf "$OUT/starferret-macos.tar.gz" -C "$STAGE" starferret
echo "Built $OUT/starferret-macos.tar.gz (version $VERSION)"

# The one line install fetches install-starferret.sh from the release, so what strangers run
# matches the bundle it downloads instead of whatever is on main that day.
cp "$ROOT/installer/macos/install-starferret.sh" "$OUT/install-starferret.sh"

# Checksums for everything the release ships, including a LibreChat bundle that
# build-librechat.sh put in dist/ first. The installer checks against this file.
(cd "$OUT" && shasum -a 256 install-starferret.sh *.tar.gz > SHA256SUMS)
echo "Wrote $OUT/SHA256SUMS"
