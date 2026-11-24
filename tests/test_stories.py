from __future__ import annotations

import hashlib
import json
from pathlib import Path

from parley.content import stories

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets" / "stories"
PACKAGED = ROOT / "src" / "parley" / "content" / "stories.json"


def _payload(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_packaged_manifest_matches_assets() -> None:
    assert PACKAGED.exists(), "run scripts/build_stories_manifest.py"
    assets = _payload(ASSETS / "manifest.json")
    packaged = _payload(PACKAGED)
    assert packaged == assets


def test_manifest_entries_are_complete() -> None:
    index = stories.load_index()
    assert index.count >= 49
    assert index.total_bytes > 0
    for story in index.stories:
        assert story.filename.endswith(".mp3")
        assert story.title
        assert story.bytes > 0
        assert len(story.sha256) == 64


def test_total_size_is_reported_in_megabytes() -> None:
    index = stories.load_index()
    assert 200 < index.total_megabytes < 400


def test_manifest_hashes_match_the_assets() -> None:
    payload = _payload(ASSETS / "manifest.json")
    for item in payload["stories"][:3]:
        digest = hashlib.sha256()
        with (ASSETS / item["filename"]).open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 256), b""):
                digest.update(block)
        assert digest.hexdigest() == item["sha256"]
