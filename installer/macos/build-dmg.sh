#!/bin/bash
# Build the StarFerret Mac app, which runs install-starferret.sh with a progress window, as a .dmg.
#
#   bash installer/macos/build-release.sh v0.1.0   # first: makes dist/starferret-macos.tar.gz
#   bash installer/macos/build-dmg.sh               # then: the .dmg in dist/
#
# Signing, all optional. Without them the app is ad hoc signed and the file is
# dist/StarFerret-early-access.dmg, with "How to open StarFerret.txt" inside
# (from early-access.md): macOS asks testers to confirm it once in System Settings.
# With them it is dist/StarFerret.dmg and opens with a double click.
#   STARFERRET_SIGN_ID   "Developer ID Application: <Company> (<TEAMID>)", in the keychain
#   NOTARY_KEY_PATH      App Store Connect API key (.p8) for notarization
#   NOTARY_KEY_ID        its key ID
#   NOTARY_ISSUER_ID     its issuer ID
#
# Needs the Xcode command line tools (swiftc, codesign, hdiutil). No Xcode project.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SRC="$ROOT/installer/macos/app"
OUT="$ROOT/dist"
BUNDLE="$OUT/starferret-macos.tar.gz"

[ "$(uname -m)" = "arm64" ] || { echo "Build on an Apple silicon Mac." >&2; exit 1; }
xcrun --find swiftc >/dev/null 2>&1 \
  || { echo "swiftc is missing. Install the Xcode command line tools: xcode-select --install" >&2; exit 1; }
[ -f "$BUNDLE" ] || { echo "Missing $BUNDLE. Run installer/macos/build-release.sh first." >&2; exit 1; }

# The app's version is the bundle's version, so the two never disagree.
VERSION="$(tar -xzOf "$BUNDLE" starferret/VERSION 2>/dev/null | head -1 || true)"
VERSION="${VERSION:-0.0.0}"
SHORT="$(printf '%s' "$VERSION" | sed 's/^v//; s/[^0-9.].*$//')"   # Info.plist wants digits and dots
SHORT="${SHORT:-0.0.0}"
BUILD="$(date +%Y%m%d%H%M)"

STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT
APP="$STAGE/dmg/StarFerret.app"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"

echo "Compiling the app"
xcrun swiftc -parse-as-library -swift-version 5 -O \
  -target arm64-apple-macos13.0 \
  -o "$APP/Contents/MacOS/StarFerret" \
  "$SRC"/*.swift

sed -e "s/__VERSION__/$SHORT/" -e "s/__BUILD__/$BUILD/" "$SRC/Info.plist" > "$APP/Contents/Info.plist"
plutil -lint "$APP/Contents/Info.plist" >/dev/null
# The app carries the installer and a full copy of StarFerret, so step 2 downloads nothing.
cp "$ROOT/installer/macos/install-starferret.sh" "$APP/Contents/Resources/install-starferret.sh"
cp "$BUNDLE" "$APP/Contents/Resources/starferret-macos.tar.gz"

SIGN_ID="${STARFERRET_SIGN_ID:-}"
if [ -n "$SIGN_ID" ]; then
  DMG_NAME="StarFerret.dmg"
  echo "Signing with $SIGN_ID"
  codesign --force --options runtime --timestamp --sign "$SIGN_ID" "$APP"
else
  DMG_NAME="StarFerret-early-access.dmg"
  echo "No STARFERRET_SIGN_ID: ad hoc signing. Early access build: testers confirm it once in System Settings."
  codesign --force --sign - "$APP"
  cp "$ROOT/installer/macos/early-access.md" "$STAGE/dmg/How to open StarFerret.txt"
fi
codesign --verify --strict --verbose=1 "$APP"
DMG="$OUT/$DMG_NAME"

ln -s /Applications "$STAGE/dmg/Applications"
rm -f "$OUT/StarFerret.dmg" "$OUT/StarFerret-early-access.dmg"
hdiutil create -quiet -volname "StarFerret" -srcfolder "$STAGE/dmg" -fs HFS+ -format UDZO "$DMG"

if [ -n "$SIGN_ID" ]; then
  codesign --force --timestamp --sign "$SIGN_ID" "$DMG"
fi

if [ -n "$SIGN_ID" ] && [ -n "${NOTARY_KEY_PATH:-}" ] && [ -n "${NOTARY_KEY_ID:-}" ] && [ -n "${NOTARY_ISSUER_ID:-}" ]; then
  echo "Sending to Apple for notarization (a few minutes)"
  xcrun notarytool submit "$DMG" \
    --key "$NOTARY_KEY_PATH" --key-id "$NOTARY_KEY_ID" --issuer "$NOTARY_ISSUER_ID" --wait
  xcrun stapler staple "$DMG"
  echo "Notarized and stapled"
elif [ -n "$SIGN_ID" ]; then
  echo "Signed but not notarized: macOS will still warn on other Macs. Set the NOTARY_* variables."
fi

# Keep the release checksums complete when build-release.sh already wrote them.
if [ -f "$OUT/SHA256SUMS" ]; then
  (cd "$OUT" && shasum -a 256 install-starferret.sh *.tar.gz "$DMG_NAME" > SHA256SUMS)
fi
echo "Built $DMG (version $VERSION, $(du -h "$DMG" | awk '{print $1}'))"
