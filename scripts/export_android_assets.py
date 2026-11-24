#!/usr/bin/env python3
"""Generate the data assets used by the Android companion app.

The desktop application is the source of truth for interface translations,
role-play scenarios and the spoken-story catalogue. This script copies those
definitions into ``packaging/android/app/src/main/assets`` so the Android app
never drifts from the desktop app.

Run it after changing ``src/parley/core/i18n.py``, the scenario list or the
story manifest::

    python scripts/export_android_assets.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from parley.core.i18n import STRINGS, UI_LANGUAGES  # noqa: E402
from parley.core.scenarios import SCENARIOS  # noqa: E402

ASSETS = ROOT / "packaging" / "android" / "app" / "src" / "main" / "assets"


def _write(name: str, payload: object) -> Path:
    path = ASSETS / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8",
    )
    return path


def export_translations() -> Path:
    payload = {
        key: {language: values.get(language, "") for language in UI_LANGUAGES}
        for key, values in STRINGS.items()
    }
    return _write("i18n.json", payload)


def export_scenarios() -> Path:
    payload = [
        {
            "id": scenario.id,
            "label": scenario.label,
            "description": scenario.description,
            "persona": scenario.persona,
            "band": scenario.band,
        }
        for scenario in SCENARIOS
    ]
    return _write("scenarios.json", payload)


def export_stories() -> Path:
    source = ROOT / "assets" / "stories" / "manifest.json"
    manifest = json.loads(source.read_text(encoding="utf-8"))
    return _write("stories.json", manifest)


def main() -> None:
    for path in (export_translations(), export_scenarios(), export_stories()):
        print(f"wrote {path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
