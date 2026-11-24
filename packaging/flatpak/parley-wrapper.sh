#!/bin/sh
# Entry point of the Flatpak build. GTK 4, PyGObject and Python come from the
# org.gnome.Platform runtime; the speech packages are installed in /app at build
# time by the manifest.

set -eu

export PARLEY_DATA_DIR="${PARLEY_DATA_DIR:-${XDG_DATA_HOME:-$HOME/.local/share}/parley}"
export PYTHONPATH="/app/share/parley/app/src${PYTHONPATH:+:$PYTHONPATH}"
export PYTHONUNBUFFERED=1
export PYTHONDONTWRITEBYTECODE=1

mkdir -p "$PARLEY_DATA_DIR"

exec /usr/bin/python3 -m parley "$@"
