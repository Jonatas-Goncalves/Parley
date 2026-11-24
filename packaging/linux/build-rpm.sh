#!/usr/bin/env bash
# Build an RPM from the working tree. Works on openSUSE Leap and Tumbleweed:
# the spec selects the python311 or python313 PyGObject package automatically.
#
# Usage: build-rpm.sh
# Output: dist/parley-<version>-1.noarch.rpm

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
VERSION="$(sed -n 's/^version = "\(.*\)"/\1/p' "$ROOT_DIR/pyproject.toml" | head -n1)"
WORK="$ROOT_DIR/build/rpm"
SOURCE_DIR="$WORK/parley-$VERSION"
TOP_DIR="$WORK/rpmbuild"
DIST="$ROOT_DIR/dist"

log() { printf '\n==> %s\n' "$*"; }
die() { printf 'Error: %s\n' "$*" >&2; exit 1; }

command -v rpmbuild >/dev/null 2>&1 || die "rpmbuild is not installed."
[ -n "$VERSION" ] || die "Could not read the version from pyproject.toml."

# Leap and Tumbleweed produce the same NEVRA but need different dependencies.
# Keep the two files apart in the release assets.
SLE_VERSION="$(rpm --eval '%{?sle_version}' 2>/dev/null || true)"
if [ -n "$SLE_VERSION" ] && [ "$SLE_VERSION" != "%{?sle_version}" ]; then
    FLAVOR="leap"
else
    FLAVOR="tumbleweed"
fi
FLAVOR="${PARLEY_RPM_FLAVOR:-$FLAVOR}"
OUTPUT="$DIST/parley-${VERSION}-1.${FLAVOR}.noarch.rpm"

log "Staging the source tree"
rm -rf "$WORK"
mkdir -p "$SOURCE_DIR" "$TOP_DIR"/{BUILD,BUILDROOT,RPMS,SOURCES,SPECS,SRPMS} "$DIST"
tar -C "$ROOT_DIR" -cf - \
    --exclude='./.git' \
    --exclude='./build' \
    --exclude='./dist' \
    --exclude='./models' \
    --exclude='./cache' \
    --exclude='./Github' \
    --exclude='./assets/Spoken Stories' \
    --exclude='./testdisk.log' \
    --exclude='./conversa.html' \
    --exclude='./conversa.md' \
    --exclude='./sessao.json' \
    --exclude='./session-*.md' \
    --exclude='__pycache__' \
    --exclude='*.pyc' \
    --exclude='.pytest_cache' \
    --exclude='.ruff_cache' \
    . | tar -C "$SOURCE_DIR" -xf -

tar -C "$WORK" -czf "$TOP_DIR/SOURCES/parley-$VERSION.tar.gz" "parley-$VERSION"

log "Writing the spec"
sed "s/^Version:.*/Version:        $VERSION/" \
    "$SCRIPT_DIR/parley.spec" > "$TOP_DIR/SPECS/parley.spec"

log "Running rpmbuild"
rpmbuild -bb \
    --define "_topdir $TOP_DIR" \
    --define "debug_package %{nil}" \
    "$TOP_DIR/SPECS/parley.spec"

BUILT="$(find "$TOP_DIR/RPMS" -name 'parley-*.rpm' -print -quit)"
[ -n "$BUILT" ] || die "rpmbuild did not produce a package."

cp -f "$BUILT" "$OUTPUT"
log "Done"
ls -lh "$OUTPUT"
