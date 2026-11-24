"""Persistent user preferences stored next to models and cache.

The file is intentionally simple JSON so users can inspect or edit it. Writes
are atomic and protected by a process-local lock.
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
from pathlib import Path

from .config import DATA_DIR

CONFIG_NAME = "config.json"
LOCK = threading.RLock()

DEFAULT_CONFIG: dict[str, object] = {
    "ui_language": "en",
    "theme": "system",
    "native": "pt",
    "target": "en",
    "backend": "ollama",
    "backend_explicit": False,
    "base_url": "",
    "model": "",
    "model_tier": "medium",
    "scenario": "meeting_someone_new",
    "level": "auto",
    "voice_mode": "continuous",
    "whisper_model": "base",
    "tts_enabled": True,
    "always_explain": True,
    "correct_errors": True,
    "stories_installed": False,
    "onboarding_done": False,
}


def config_path() -> Path:
    configured = os.environ.get("PARLEY_CONFIG", "").strip()
    if configured:
        return Path(configured).expanduser()
    return DATA_DIR / CONFIG_NAME


def load() -> dict[str, object]:
    path = config_path()
    data = dict(DEFAULT_CONFIG)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            data.update({key: value for key, value in raw.items() if value is not None})
    except (OSError, ValueError):
        pass
    return data


def save(updates: dict[str, object]) -> dict[str, object]:
    with LOCK:
        data = load()
        data.update(updates)
        path = config_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        handle, temporary = tempfile.mkstemp(
            prefix=".config-", suffix=".json", dir=str(path.parent)
        )
        try:
            with os.fdopen(handle, "w", encoding="utf-8") as stream:
                json.dump(data, stream, ensure_ascii=False, indent=2)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        finally:
            try:
                os.unlink(temporary)
            except OSError:
                pass
        return data


def set_value(key: str, value: object) -> dict[str, object]:
    return save({key: value})


def get(key: str, default: object = None) -> object:
    return load().get(key, DEFAULT_CONFIG.get(key, default))
