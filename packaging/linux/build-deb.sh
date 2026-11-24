#!/usr/bin/env bash
# Build the Debian package. Run from any directory; output goes to dist/.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
VERSION="$(sed -n 's/^version = "\(.*\)"/\1/p' "$ROOT_DIR/pyproject.toml" | head -n1)"
STAGE="$ROOT_DIR/build/deb/parley"
DIST="$ROOT_DIR/dist"
OUTPUT="$DIST/parley_${VERSION}_all.deb"

log() { printf '\n==> %s\n' "$*"; }
die() { printf 'Error: %s\n' "$*" >&2; exit 1; }

command -v dpkg-deb >/dev/null 2>&1 || die "dpkg-deb is not installed."

[ -n "$VERSION" ] || die "Could not read the version from pyproject.toml."

log "Staging files"
rm -rf "$STAGE"
mkdir -p "$STAGE/DEBIAN" "$DIST"
bash "$SCRIPT_DIR/stage-app.sh" "$ROOT_DIR" "$STAGE/usr"

log "Writing package metadata"
INSTALLED_SIZE="$(du -sk "$STAGE/usr" | cut -f1)"
cat > "$STAGE/DEBIAN/control" <<EOF
Package: parley
Version: ${VERSION}
Section: education
Priority: optional
Architecture: all
Installed-Size: ${INSTALLED_SIZE}
Maintainer: Parley contributors <parley@users.noreply.github.com>
Homepage: https://github.com/Jonatas-Goncalves/Parley
Depends: python3 (>= 3.11), python3-venv, python3-gi, gir1.2-gtk-4.0, libportaudio2, libsndfile1, ffmpeg, ca-certificates, fonts-noto-cjk
Recommends: ollama
Description: Local voice-first language tutor
 Parley is a desktop language tutor that runs entirely on your computer.
 It combines a local language model, speech recognition and speech synthesis
 for Portuguese, English, Spanish, French, Italian, Japanese, Korean and
 Mandarin Chinese.
 .
 The interface is built with GTK 4. Voice Practice offers 19 role-play
 scenarios, Pronunciation compares your reading with a generated phrase,
 Spoken Stories plays public-domain recordings, and Complete the Sentence
 trains listening and spelling.
 .
 No account, cloud service or telemetry is used.
EOF

cat > "$STAGE/DEBIAN/postinst" <<'EOF'
#!/bin/sh
set -e
if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database /usr/share/applications >/dev/null 2>&1 || true
fi
if command -v gtk-update-icon-cache >/dev/null 2>&1; then
    gtk-update-icon-cache -f -t /usr/share/icons/hicolor >/dev/null 2>&1 || true
fi
exit 0
EOF
chmod 0755 "$STAGE/DEBIAN/postinst"

cat > "$STAGE/DEBIAN/prerm" <<'EOF'
#!/bin/sh
set -e
exit 0
EOF
chmod 0755 "$STAGE/DEBIAN/prerm"

log "Building $OUTPUT"
rm -f "$OUTPUT"
dpkg-deb --root-owner-group --build "$STAGE" "$OUTPUT"

log "Done"
ls -lh "$OUTPUT"
