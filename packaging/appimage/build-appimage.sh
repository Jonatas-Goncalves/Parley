#!/usr/bin/env bash
# Build an AppImage from the working tree.
#
# The AppImage reuses the host GTK 4, PyGObject and Python, and prepares the
# speech packages in the user data folder on first start.
#
# Usage: build-appimage.sh
# Output: dist/Parley-<version>-x86_64.AppImage

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
VERSION="$(sed -n 's/^version = "\(.*\)"/\1/p' "$ROOT_DIR/pyproject.toml" | head -n1)"
APP_ID="io.github.jonatasgoncalves.Parley"
BUILD_DIR="$ROOT_DIR/build/appimage"
APPDIR="$BUILD_DIR/AppDir"
TOOLS_DIR="$BUILD_DIR/tools"
DIST="$ROOT_DIR/dist"
OUTPUT="$DIST/Parley-${VERSION}-x86_64.AppImage"

CJK_FONT_URL="https://raw.githubusercontent.com/notofonts/noto-cjk/main/Sans/OTC/NotoSansCJK-Regular.ttc"
CJK_FONT_SHA256="b76b0433203017ca80401b2ee0dd69350349871c4b19d504c34dbdd80541690a"
CJK_LICENSE_URL="https://raw.githubusercontent.com/notofonts/noto-cjk/main/Sans/LICENSE"
CJK_LICENSE_SHA256="6a73f9541c2de74158c0e7cf6b0a58ef774f5a780bf191f2d7ec9cc53efe2bf2"

log() { printf '\n==> %s\n' "$*"; }
die() { printf 'Error: %s\n' "$*" >&2; exit 1; }

CA_FLAGS=()
if [ ! -e /etc/ssl/ca-bundle.pem ] \
    && [ ! -e /var/lib/ca-certificates/ca-bundle.pem ] \
    && [ -f "$ROOT_DIR/assets/cacert.pem" ]; then
    CA_FLAGS=(--cacert "$ROOT_DIR/assets/cacert.pem")
fi

download_verified() {
    url="$1"
    expected="$2"
    target="$3"
    if [ -f "$target" ] \
        && [ "$(sha256sum "$target" | awk '{print $1}')" = "$expected" ]; then
        return 0
    fi
    partial="${target}.part"
    curl -fL --retry 3 --connect-timeout 20 "${CA_FLAGS[@]}" -o "$partial" "$url"
    if [ "$(sha256sum "$partial" | awk '{print $1}')" != "$expected" ]; then
        rm -f "$partial"
        die "Checksum mismatch for $url"
    fi
    mv "$partial" "$target"
}

[ -n "$VERSION" ] || die "Could not read the version from pyproject.toml."

log "Staging the application"
rm -rf "$APPDIR"
mkdir -p "$APPDIR" "$TOOLS_DIR" "$DIST"
bash "$ROOT_DIR/packaging/linux/stage-app.sh" "$ROOT_DIR" "$APPDIR/usr"

log "Bundling Noto Sans CJK"
FONT_DIR="$APPDIR/usr/share/fonts/noto-cjk"
FONT_CACHE="$BUILD_DIR/fonts"
install -d "$FONT_DIR" "$FONT_CACHE"
download_verified "$CJK_FONT_URL" "$CJK_FONT_SHA256" \
    "$FONT_CACHE/NotoSansCJK-Regular.ttc"
download_verified "$CJK_LICENSE_URL" "$CJK_LICENSE_SHA256" \
    "$FONT_CACHE/LICENSE.txt"
install -m 0644 "$FONT_CACHE/NotoSansCJK-Regular.ttc" "$FONT_DIR/"
install -m 0644 "$FONT_CACHE/LICENSE.txt" "$FONT_DIR/"

cat > "$APPDIR/AppRun" <<'EOF'
#!/bin/sh
set -eu
HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
export PARLEY_PREFIX="$HERE/usr/lib/parley"
export PARLEY_DATA_DIR="${PARLEY_DATA_DIR:-${XDG_DATA_HOME:-$HOME/.local/share}/parley}"
export PYTHONUNBUFFERED=1
mkdir -p "$PARLEY_DATA_DIR"

FONT_DIR="$HERE/usr/share/fonts/noto-cjk"
if [ -d "$FONT_DIR" ]; then
    FONT_CACHE="${XDG_CACHE_HOME:-$HOME/.cache}/parley"
    if mkdir -p "$FONT_CACHE" 2>/dev/null; then
        FONT_CONF="$FONT_CACHE/fonts.conf"
        if cat > "$FONT_CONF" <<XML
<?xml version="1.0"?>
<!DOCTYPE fontconfig SYSTEM "fonts.dtd">
<fontconfig>
  <include ignore_missing="yes">/etc/fonts/fonts.conf</include>
  <dir>$FONT_DIR</dir>
</fontconfig>
XML
        then
            export FONTCONFIG_FILE="$FONT_CONF"
        fi
    fi
fi

exec "$HERE/usr/bin/parley" "$@"
EOF
chmod 0755 "$APPDIR/AppRun"

install -m 0644 "$ROOT_DIR/assets/icons/parley-512.png" "$APPDIR/$APP_ID.png"
cp "$APPDIR/$APP_ID.png" "$APPDIR/.DirIcon"
sed \
    -e "s|^Exec=.*|Exec=AppRun|" \
    -e "s|^Icon=.*|Icon=$APP_ID|" \
    "$ROOT_DIR/packaging/linux/$APP_ID.desktop" \
    > "$APPDIR/$APP_ID.desktop"
chmod 0644 "$APPDIR/$APP_ID.desktop"
install -d "$APPDIR/usr/share/applications" "$APPDIR/usr/share/metainfo"
install -m 0644 "$APPDIR/$APP_ID.desktop" "$APPDIR/usr/share/applications/$APP_ID.desktop"
install -m 0644 \
    "$ROOT_DIR/packaging/linux/$APP_ID.metainfo.xml" \
    "$APPDIR/usr/share/metainfo/$APP_ID.metainfo.xml"

log "Fetching appimagetool"
TOOL="$TOOLS_DIR/appimagetool-x86_64.AppImage"
RUNTIME="$TOOLS_DIR/runtime-x86_64"
if [ ! -x "$TOOL" ]; then
    curl -fL --retry 3 --connect-timeout 20 "${CA_FLAGS[@]}" -o "$TOOL" \
        "https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage"
    chmod +x "$TOOL"
fi
if [ ! -s "$RUNTIME" ]; then
    curl -fL --retry 3 --connect-timeout 20 "${CA_FLAGS[@]}" -o "$RUNTIME" \
        "https://github.com/AppImage/type2-runtime/releases/download/continuous/runtime-x86_64"
fi

log "Building $OUTPUT"
rm -f "$OUTPUT"
if ! ARCH=x86_64 "$TOOL" --no-appstream --runtime-file "$RUNTIME" \
        "$APPDIR" "$OUTPUT"; then
    log "FUSE is unavailable; retrying with extraction"
    ARCH=x86_64 APPIMAGE_EXTRACT_AND_RUN=1 \
        "$TOOL" --no-appstream --runtime-file "$RUNTIME" \
        "$APPDIR" "$OUTPUT"
fi

[ -s "$OUTPUT" ] || die "The AppImage was not produced."
chmod +x "$OUTPUT"
log "Done"
ls -lh "$OUTPUT"
