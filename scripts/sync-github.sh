#!/usr/bin/env bash
# Copy the publishable tree into the clean GitHub clone.
#
#   ./scripts/sync-github.sh [destination] [--dry-run]
#
# The default destination is Github/Parley. Nothing is staged, committed or
# pushed: review the result and commit it yourself.

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEST="${1:-$ROOT_DIR/Github/Parley}"
DRY_RUN="${2:-}"

[ -d "$DEST/.git" ] || {
    printf 'Error: %s is not a git clone.\n' "$DEST" >&2
    exit 1
}

command -v rsync >/dev/null 2>&1 || {
    printf 'Error: rsync is required.\n' >&2
    exit 1
}

PATHS=(.github src assets docs packaging scripts tests)
FILES=(pyproject.toml requirements.txt README.md LICENSE .gitignore)

RSYNC_FLAGS=(-a --delete --human-readable)
if [ "$DRY_RUN" = "--dry-run" ]; then
    RSYNC_FLAGS+=(--dry-run --itemize-changes)
fi

EXCLUDES=(
    --exclude='__pycache__/'
    --exclude='*.pyc'
    --exclude='.pytest_cache/'
    --exclude='.ruff_cache/'
    --exclude='*.part'
    --exclude='Spoken Stories/'
    --exclude='build/'
    --exclude='dist/'
    --exclude='.conda/'
    --exclude='.micromamba/'
    --exclude='release/'
    --exclude='AppDir/'
    --exclude='linux/deb/'
    --exclude='assets/fonts/'
    --exclude='.android-sdk/'
    --exclude='.gradle/'
    --exclude='local.properties'
)

printf '==> Syncing %s\n' "$DEST"
for path in "${PATHS[@]}"; do
    source="$ROOT_DIR/$path"
    [ -e "$source" ] || continue
    parent="$(dirname "$path")"
    mkdir -p "$DEST/$parent"
    rsync "${RSYNC_FLAGS[@]}" "${EXCLUDES[@]}" \
        "$source" "$DEST/$parent/"
done

for path in "${FILES[@]}"; do
    [ -e "$ROOT_DIR/$path" ] || continue
    rsync "${RSYNC_FLAGS[@]}" "$ROOT_DIR/$path" "$DEST/"
done

# Remove top-level entries that no longer belong to the project.
KEEP=" .github src assets docs packaging scripts tests "
for path in "${FILES[@]}"; do
    KEEP="$KEEP$(basename "$path") "
done
for entry in "$DEST"/* "$DEST"/.[!.]*; do
    [ -e "$entry" ] || continue
    name="$(basename "$entry")"
    [ "$name" = ".git" ] && continue
    case "$KEEP" in
        *" $name "*) ;;
        *)
            if [ "$DRY_RUN" = "--dry-run" ]; then
                printf 'would remove %s\n' "$name"
            else
                rm -rf "$entry"
            fi
            ;;
    esac
done

printf '\nDone. Review the changes and commit them yourself:\n'
printf '  cd %s && git status\n' "$DEST"
