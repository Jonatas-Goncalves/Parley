#!/usr/bin/env bash
# Copy the Parley application tree into a packaging staging root.
#
# Usage: stage-app.sh <project-root> <staging-prefix>
#
# <staging-prefix> is the directory that maps to /usr inside the package, for
# example build/deb/parley/usr or an AppDir/usr. Story audio and the test suite
# are never installed; the catalogue itself lives inside the Python package.

set -euo pipefail

ROOT_DIR="$(cd "${1:?project root is required}" && pwd)"
PREFIX="${2:?staging prefix is required}"

APP_VERSION="$(sed -n 's/^version = "\(.*\)"/\1/p' "$ROOT_DIR/pyproject.toml" | head -n1)"
[ -n "$APP_VERSION" ] || {
    printf 'Could not read the version from pyproject.toml\n' >&2
    exit 1
}

APP_DIR="$PREFIX/lib/parley"
PAYLOAD="$APP_DIR/app"
ICON_THEME="$PREFIX/share/icons/hicolor"

install -d \
    "$PREFIX/bin" \
    "$APP_DIR" \
    "$PAYLOAD" \
    "$PREFIX/share/applications" \
    "$PREFIX/share/metainfo" \
    "$PREFIX/share/doc/parley"

copy_tree() {
    local source="$1"
    local destination="$2"
    mkdir -p "$destination"
    tar -C "$source" -cf - \
        --exclude='__pycache__' \
        --exclude='*.pyc' \
        --exclude='.pytest_cache' \
        --exclude='.ruff_cache' \
        . | tar -C "$destination" -xf -
}

install -m 0755 "$ROOT_DIR/packaging/linux/parley" "$PREFIX/bin/parley"
install -m 0755 "$ROOT_DIR/packaging/linux/bootstrap.py" "$APP_DIR/bootstrap.py"

copy_tree "$ROOT_DIR/src" "$PAYLOAD/src"
install -d "$PAYLOAD/assets"
install -m 0644 "$ROOT_DIR/assets/cacert.pem" "$PAYLOAD/assets/cacert.pem"
copy_tree "$ROOT_DIR/assets/icons" "$PAYLOAD/assets/icons"
install -m 0644 "$ROOT_DIR/requirements.txt" "$PAYLOAD/requirements.txt"

install -m 0644 \
    "$ROOT_DIR/packaging/linux/io.github.jonatasgoncalves.Parley.desktop" \
    "$PREFIX/share/applications/io.github.jonatasgoncalves.Parley.desktop"
install -m 0644 \
    "$ROOT_DIR/packaging/linux/io.github.jonatasgoncalves.Parley.metainfo.xml" \
    "$PREFIX/share/metainfo/io.github.jonatasgoncalves.Parley.metainfo.xml"

for size in 16 32 48 64 128 256 512; do
    install -d "$ICON_THEME/${size}x${size}/apps"
    install -m 0644 \
        "$ROOT_DIR/assets/icons/parley-${size}.png" \
        "$ICON_THEME/${size}x${size}/apps/io.github.jonatasgoncalves.Parley.png"
done

install -m 0644 "$ROOT_DIR/README.md" "$PREFIX/share/doc/parley/README.md"
install -m 0644 "$ROOT_DIR/LICENSE" "$PREFIX/share/doc/parley/LICENSE"
copy_tree "$ROOT_DIR/docs" "$PREFIX/share/doc/parley/docs"

printf '%s\n' "$APP_VERSION" > "$APP_DIR/VERSION"

# A checkout can carry restrictive modes (0600) from the machine that created
# it. Packages and AppImages are read by other users, so make the staged tree
# world-readable and keep the executable bits that are already set.
chmod -R a+rX "$PREFIX"
