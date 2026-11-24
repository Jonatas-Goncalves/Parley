"""Spoken stories catalogue and on-demand download.

The audio files live in the repository under ``assets/stories`` but are not
shipped inside the installers. Settings offers a download that copies them to
the user data folder, one file at a time, with hash verification.
"""

from __future__ import annotations

import hashlib
import json
import os
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

from ..core.config import DATA_DIR, ROOT_DIR

DEFAULT_BASE_URL = (
    "https://raw.githubusercontent.com/Jonatas-Goncalves/Parley/master/assets/stories"
)


def base_url() -> str:
    return os.environ.get("PARLEY_STORIES_URL", DEFAULT_BASE_URL).rstrip("/")


def local_dir() -> Path:
    configured = os.environ.get("PARLEY_STORIES_DIR", "").strip()
    if configured:
        return Path(configured).expanduser()
    return DATA_DIR / "stories"


def manifest_candidates() -> list[Path]:
    candidates = []
    configured = os.environ.get("PARLEY_STORIES_MANIFEST", "").strip()
    if configured:
        candidates.append(Path(configured).expanduser())
    candidates.extend(
        [
            local_dir() / "manifest.json",
            ROOT_DIR / "assets" / "stories" / "manifest.json",
            Path(__file__).with_name("stories.json"),
        ]
    )
    return candidates


@dataclass(frozen=True)
class Story:
    title: str
    author: str
    filename: str
    bytes: int = 0
    seconds: float = 0.0
    sha256: str = ""

    @property
    def megabytes(self) -> float:
        return self.bytes / (1024 * 1024)


@dataclass
class StoryIndex:
    stories: list[Story] = field(default_factory=list)

    @property
    def count(self) -> int:
        return len(self.stories)

    @property
    def total_bytes(self) -> int:
        return sum(story.bytes for story in self.stories)

    @property
    def total_megabytes(self) -> float:
        return self.total_bytes / (1024 * 1024)


def _story_from_item(item: dict) -> Story | None:
    filename = str(item.get("filename") or item.get("name") or "").strip()
    if not filename or not filename.lower().endswith(".mp3"):
        return None
    title = str(item.get("title") or "").strip()
    author = str(item.get("author") or "").strip()
    if not title:
        stem = Path(filename).stem
        # Best-effort readable title from filename.
        cleaned = stem.replace("_-_By_", " - ").replace("_", " ").strip()
        if " - " in cleaned:
            title_part, author_part = cleaned.split(" - ", 1)
            title = title_part.strip() or stem
            if not author:
                author = author_part.strip()
        else:
            title = cleaned or stem
    return Story(
        title=title,
        author=author,
        filename=filename,
        bytes=int(item.get("bytes") or item.get("size") or 0),
        seconds=float(item.get("seconds") or 0.0),
        sha256=str(item.get("sha256") or ""),
    )


def load_index() -> StoryIndex:
    for path in manifest_candidates():
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        items = payload.get("stories") if isinstance(payload, dict) else payload
        if not isinstance(items, list):
            continue
        stories = []
        for item in items:
            if not isinstance(item, dict):
                continue
            story = _story_from_item(item)
            if story is not None:
                stories.append(story)
        if stories:
            return StoryIndex(stories)
    return StoryIndex()


def remote_index(timeout: float = 8.0) -> StoryIndex:
    """Fetch available story files from GitHub. Falls back to local manifest."""
    api = os.environ.get(
        "PARLEY_STORIES_API",
        "https://api.github.com/repos/Jonatas-Goncalves/Parley/contents/assets/stories?ref=master",
    )
    try:
        req = urllib.request.Request(
            api,
            headers={
                "Accept": "application/vnd.github+json",
                "User-Agent": "Parley/1.0",
            },
        )
        with urllib.request.urlopen(req, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
        if not isinstance(payload, list):
            return load_index()
        stories = []
        for item in payload:
            if not isinstance(item, dict):
                continue
            if item.get("type") != "file":
                continue
            story = _story_from_item(item)
            if story is not None:
                stories.append(story)
        if stories:
            stories.sort(key=lambda s: s.filename.lower())
            return StoryIndex(stories)
    except Exception:
        pass
    return load_index()


def scan_local() -> StoryIndex:
    """List story files actually present locally (downloaded or bundled)."""
    found: dict[str, Story] = {}

    # Prefer manifest metadata when available.
    manifest = load_index()
    meta = {s.filename: s for s in manifest.stories}

    dirs = [local_dir(), ROOT_DIR / "assets" / "stories"]
    for directory in dirs:
        if not directory.exists():
            continue
        for path in sorted(directory.glob("*.mp3")):
            if not path.is_file() or path.stat().st_size <= 0:
                continue
            name = path.name
            if name in found:
                continue
            base = meta.get(name)
            if base is not None:
                found[name] = Story(
                    title=base.title,
                    author=base.author,
                    filename=name,
                    bytes=path.stat().st_size,
                    seconds=base.seconds,
                    sha256=base.sha256,
                )
            else:
                story = _story_from_item({"filename": name, "size": path.stat().st_size})
                if story is not None:
                    found[name] = story
    stories = list(found.values())
    stories.sort(key=lambda s: s.filename.lower())
    return StoryIndex(stories)


def local_path(story: Story) -> Path:
    return local_dir() / story.filename


def is_installed(story: Story) -> bool:
    path = local_path(story)
    return path.exists() and path.stat().st_size > 0


def installed_bytes() -> int:
    directory = local_dir()
    if not directory.exists():
        return 0
    return sum(
        path.stat().st_size for path in directory.glob("*.mp3") if path.is_file()
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 256), b""):
            digest.update(block)
    return digest.hexdigest()


def download(
    index: StoryIndex,
    progress=None,
    should_stop=None,
) -> list[str]:
    """Download missing stories. Returns the list of error messages."""

    directory = local_dir()
    directory.mkdir(parents=True, exist_ok=True)
    errors: list[str] = []
    total = index.total_bytes or 1
    completed = 0
    for position, story in enumerate(index.stories, start=1):
        if should_stop and should_stop():
            break
        target = directory / story.filename
        if target.exists() and target.stat().st_size > 0:
            completed += story.bytes
            if progress:
                progress(position, index.count, completed, total, story.title)
            continue
        url = f"{base_url()}/{story.filename}"
        temporary = target.with_suffix(target.suffix + ".part")
        try:
            with urllib.request.urlopen(url, timeout=60) as response:
                with temporary.open("wb") as handle:
                    while True:
                        if should_stop and should_stop():
                            raise InterruptedError("cancelled")
                        block = response.read(1024 * 256)
                        if not block:
                            break
                        handle.write(block)
                        completed += len(block)
                        if progress:
                            progress(position, index.count, completed, total, story.title)
            if story.sha256 and _sha256(temporary) != story.sha256:
                raise ValueError("checksum mismatch")
            temporary.replace(target)
        except InterruptedError:
            temporary.unlink(missing_ok=True)
            break
        except Exception as exc:
            temporary.unlink(missing_ok=True)
            errors.append(f"{story.filename}: {exc}")
        if progress:
            progress(position, index.count, completed, total, story.title)
    return errors


def remove_all() -> None:
    directory = local_dir()
    if not directory.exists():
        return
    for path in directory.glob("*.mp3"):
        path.unlink(missing_ok=True)
    for path in directory.glob("*.part"):
        path.unlink(missing_ok=True)


def source_path(story: Story) -> Path:
    """Return the first readable copy: downloaded, then the repo checkout."""

    downloaded = local_path(story)
    if downloaded.exists() and downloaded.stat().st_size > 0:
        return downloaded
    return ROOT_DIR / "assets" / "stories" / story.filename


def resolved_path(story: Story) -> Path | None:
    path = source_path(story)
    return path if path.exists() and path.stat().st_size > 0 else None
