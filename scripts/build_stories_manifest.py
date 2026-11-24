"""Generate assets/stories/manifest.json from the audio files in the repo."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = ROOT / "assets" / "Spoken Stories"
DEFAULT_TARGET = ROOT / "assets" / "stories"

PART_RE = re.compile(r"_+Part_(\d+)$", re.IGNORECASE)


def clean_name(stem: str) -> tuple[str, str]:
    value = stem.replace("_", " ").strip()
    value = re.sub(r"\s+", " ", value)
    author = ""
    if " - By " in value:
        value, author = value.split(" - By ", 1)
    title = value.replace(" - ", ": ").strip(" -")
    title = re.sub(r":\s*$", "", title)
    return title, author.strip()


def duration(path: Path) -> float:
    if not shutil.which("ffprobe"):
        return 0.0
    try:
        output = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(path),
            ],
            capture_output=True,
            text=True,
            check=True,
            timeout=30,
        )
        return round(float(output.stdout.strip()), 1)
    except Exception:
        return 0.0


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 256), b""):
            digest.update(block)
    return digest.hexdigest()


def trim_padding(path: Path) -> int:
    """Remove zero padding at the start or end of an MP3 file.

    Some sources pad the recording with zero bytes. libsndfile and libmpg123
    stop at the first invalid header, so a padded file cannot be played even
    though its duration looks correct. Zero bytes are never part of an MP3
    frame header, so removing a run at the edges is safe.
    """

    data = path.read_bytes()
    start = 0
    end = len(data)
    while start < end and data[start] == 0:
        start += 1
    while end > start and data[end - 1] == 0:
        end -= 1
    if start == 0 and end == len(data):
        return 0
    path.write_bytes(data[start:end])
    return len(data) - (end - start)


def normalise(source: Path, target: Path) -> None:
    target.mkdir(parents=True, exist_ok=True)
    for path in sorted(source.iterdir()):
        if path.suffix.lower() != ".mp3":
            continue
        destination = target / (path.stem + ".mp3")
        if path.resolve() == destination.resolve():
            continue
        if not destination.exists():
            shutil.move(str(path), str(destination))


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the spoken stories manifest")
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--target", type=Path, default=DEFAULT_TARGET)
    parser.add_argument("--no-move", action="store_true")
    args = parser.parse_args()

    if not args.no_move and args.source.exists():
        normalise(args.source, args.target)

    files = sorted(args.target.glob("*.mp3"))
    if not files:
        print(f"No mp3 files found in {args.target}")
        return 1

    stories = []
    total = 0
    padding = 0
    for path in files:
        padding += trim_padding(path)
        title, author = clean_name(path.stem)
        size = path.stat().st_size
        total += size
        stories.append(
            {
                "title": title,
                "author": author,
                "filename": path.name,
                "bytes": size,
                "seconds": duration(path),
                "sha256": sha256(path),
            }
        )
    manifest = {"version": 1, "stories": stories}
    output = args.target / "manifest.json"
    output.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    output_copy = ROOT / "src" / "parley" / "content" / "stories.json"
    output_copy.parent.mkdir(parents=True, exist_ok=True)
    output_copy.write_text(output.read_text(encoding="utf-8"), encoding="utf-8")
    print(f"{len(stories)} stories, {total / (1024 * 1024):.1f} MB -> {output}")
    if padding:
        print(f"Removed {padding / (1024 * 1024):.1f} MB of zero padding")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
