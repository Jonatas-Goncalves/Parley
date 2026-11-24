#!/usr/bin/env bash
# Build the Flatpak.
#
#   ./packaging/flatpak/build-flatpak.sh            build and install for the user
#   ./packaging/flatpak/build-flatpak.sh --export   build a .flatpak bundle in dist/
#
# The first run downloads org.gnome.Platform/Sdk and the speech packages, so it
# can take a while.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
APP_ID="io.github.jonatasgoncalves.Parley"
MANIFEST="$SCRIPT_DIR/$APP_ID.yml"
VERSION="$(sed -n 's/^version = "\(.*\)"/\1/p' "$ROOT_DIR/pyproject.toml" | head -n1)"
BUILD_DIR="$ROOT_DIR/build/flatpak/build"
REPO_DIR="$ROOT_DIR/build/flatpak/repo"
STATE_DIR="$ROOT_DIR/build/flatpak/state"
DIST="$ROOT_DIR/dist"

log() { printf '\n==> %s\n' "$*"; }
die() { printf 'Error: %s\n' "$*" >&2; exit 1; }

command -v flatpak-builder >/dev/null 2>&1 || die \
    "flatpak-builder is not installed. On openSUSE: sudo zypper install flatpak-builder"

if ! flatpak remotes --user | grep -q '^flathub'; then
    log "Adding the Flathub repository"
    flatpak remote-add --user --if-not-exists flathub \
        https://flathub.org/repo/flathub.flatpakrepo
fi

mkdir -p "$BUILD_DIR" "$STATE_DIR" "$DIST"
cd "$ROOT_DIR"

if [ "${1:-}" = "--export" ]; then
    OUTPUT="$DIST/Parley-${VERSION}.flatpak"
    rm -rf "$REPO_DIR" "$OUTPUT"
    log "Building the Flatpak repository"
    flatpak-builder \
        --user \
        --force-clean \
        --disable-rofiles-fuse \
        --default-branch=stable \
        --install-deps-from=flathub \
        --repo="$REPO_DIR" \
        --state-dir="$STATE_DIR" \
        "$BUILD_DIR" \
        "$MANIFEST"
    log "Bundling $OUTPUT"
    flatpak build-bundle "$REPO_DIR" "$OUTPUT" "$APP_ID" stable \
        --runtime-repo=https://flathub.org/repo/flathub.flatpakrepo
    ls -lh "$OUTPUT"
else
    log "Building and installing the Flatpak for the current user"
    flatpak-builder \
        --user \
        --force-clean \
        --disable-rofiles-fuse \
        --install \
        --install-deps-from=flathub \
        --state-dir="$STATE_DIR" \
        "$BUILD_DIR" \
        "$MANIFEST"
    log "Done. Run: flatpak run $APP_ID"
fi
