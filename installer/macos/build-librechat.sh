#!/bin/bash
# Build LibreChat once, on an Apple silicon Mac, so customers unpack it instead of
# compiling it for ten minutes. The release workflow runs this before build-release.sh.
#
#   bash installer/macos/build-librechat.sh            # version from install-starferret.sh
#   bash installer/macos/build-librechat.sh v0.8.8     # a specific tag
#
# Output: dist/librechat-<version>-darwin-arm64.tar.gz, holding one `librechat/` folder
# with node_modules and the built front end. Needs Node.js 24 (the same line the
# installer's private Node.js uses), because the native modules are built for it.
# Downloads LibreChat's source and its npm packages: about 1 to 2 GB.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
# One place for the version: the installer.
DEFAULT_VERSION="$(sed -n 's/^LIBRECHAT_VERSION="\${STARFERRET_LIBRECHAT_VERSION:-\(v[^}]*\)}".*/\1/p' "$ROOT/installer/macos/install-starferret.sh")"
VERSION="${1:-$DEFAULT_VERSION}"
[ -n "$VERSION" ] || { echo "Could not read LIBRECHAT_VERSION from install-starferret.sh. Pass a version, like v0.8.8." >&2; exit 1; }

[ "$(uname -s)" = "Darwin" ] && [ "$(uname -m)" = "arm64" ] \
  || { echo "Build this on an Apple silicon Mac. Native modules are built for the machine running the build." >&2; exit 1; }
NODE_MAJOR="$(node -p 'process.versions.node.split(".")[0]' 2>/dev/null || echo none)"
[ "$NODE_MAJOR" = "24" ] \
  || { echo "Needs Node.js 24 (found: $NODE_MAJOR). The installer runs LibreChat on Node.js 24." >&2; exit 1; }

OUT="$ROOT/dist"
NAME="librechat-$VERSION-darwin-arm64.tar.gz"
STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT
mkdir -p "$STAGE/librechat" "$OUT"

echo "Downloading LibreChat $VERSION"
curl -fsSL -o "$STAGE/src.tar.gz" "https://github.com/danny-avila/LibreChat/archive/refs/tags/$VERSION.tar.gz"
tar -xzf "$STAGE/src.tar.gz" -C "$STAGE/librechat" --strip-components=1
rm -f "$STAGE/src.tar.gz"

echo "Installing packages and building the front end"
(
  cd "$STAGE/librechat"
  npm ci --no-audit --no-fund --loglevel=error
  npm run frontend
  # The built front end and packages stay; build only tools go. Keeps the download small.
  npm prune --omit=dev --no-audit --no-fund --loglevel=error
)
printf '%s\n' "$VERSION" > "$STAGE/librechat/.starferret-version"

tar -czf "$OUT/$NAME" -C "$STAGE" librechat
echo "Built $OUT/$NAME ($(du -h "$OUT/$NAME" | awk '{print $1}'))"
