"""Small helpers for checking whether the system can render CJK text."""

from __future__ import annotations

import os
from pathlib import Path

CJK_LANGUAGES = {"zh", "ko", "ja"}

# Font families commonly shipped for Chinese, Japanese and Korean.
KNOWN_FAMILIES = (
    "noto sans cjk",
    "noto serif cjk",
    "source han",
    "wenquanyi",
    "wqy",
    "droid sans fallback",
    "arphic",
    "uming",
    "ukai",
    "ipa",
    "takao",
    "vl gothic",
    "baekmuk",
    "nanum",
    "malgun",
    "meiryo",
    "yu gothic",
    "ms gothic",
    "simsun",
    "simhei",
    "microsoft yahei",
    "pingfang",
    "hiragino",
)

KNOWN_FILES = (
    "NotoSansCJK*.ttc",
    "NotoSerifCJK*.ttc",
    "*SourceHan*.otf",
    "wqy-*.ttc",
    "DroidSansFallback*.ttf",
    "msyh.ttc",
    "malgun.ttf",
    "YuGoth*.ttc",
    "msgothic.ttc",
    "meiryo.ttc",
    "simsun.ttc",
)


def _family_matches(name: str) -> bool:
    lowered = (name or "").casefold()
    return any(marker in lowered for marker in KNOWN_FAMILIES)


def _font_directories() -> list[Path]:
    directories = [
        Path("/usr/share/fonts"),
        Path("/usr/local/share/fonts"),
        Path.home() / ".local/share/fonts",
        Path.home() / ".fonts",
    ]
    windows = os.environ.get("WINDIR") or os.environ.get("SystemRoot")
    if windows:
        directories.append(Path(windows) / "Fonts")
    return [directory for directory in directories if directory.exists()]


def cjk_font_available() -> bool:
    """Return True when a CJK-capable font family is installed."""

    try:
        import gi

        gi.require_version("PangoCairo", "1.0")

        from gi.repository import PangoCairo

        font_map = PangoCairo.font_map_get_default()
        families = {family.get_name() for family in font_map.list_families()}
        if any(_family_matches(name) for name in families):
            return True
    except Exception:
        pass

    # Fallback for environments without PangoCairo (for example a server
    # install): look for the well-known font files on disk.
    for directory in _font_directories():
        for pattern in KNOWN_FILES:
            try:
                if any(directory.rglob(pattern)):
                    return True
            except OSError:
                continue
    return False


def needs_cjk_font(language: str) -> bool:
    return (language or "").lower() in CJK_LANGUAGES
