"""PyInstaller entry point. Kept outside the package so relative imports work."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def _bundle_dir() -> Path:
    """Return the folder that holds the bundled data files."""

    if getattr(sys, "frozen", False):
        internal = getattr(sys, "_MEIPASS", "")
        if internal:
            return Path(internal)
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def _register_private_font(font_file: Path) -> None:
    """Make the bundled font visible to GDI-based text rendering."""

    if not font_file.is_file():
        return
    try:
        import ctypes

        FR_PRIVATE = 0x10
        ctypes.windll.gdi32.AddFontResourceExW(str(font_file), FR_PRIVATE, 0)
    except Exception:
        # Rendering still works when Windows already ships CJK fonts.
        pass


def _configure_cjk_font() -> None:
    base = _bundle_dir()
    font_dir = base / "share" / "fonts" / "noto-cjk"
    if not font_dir.is_dir():
        return

    _register_private_font(font_dir / "NotoSansCJK-Regular.ttc")

    cache_root = os.environ.get("LOCALAPPDATA") or os.environ.get("TEMP")
    cache = Path(cache_root) / "Parley" / "fontconfig" if cache_root else base / "fontconfig"
    try:
        cache.mkdir(parents=True, exist_ok=True)
    except OSError:
        return

    config_dir = base / "etc" / "fonts"
    config = cache / "fonts.conf"
    lines = [
        '<?xml version="1.0"?>',
        '<!DOCTYPE fontconfig SYSTEM "fonts.dtd">',
        "<fontconfig>",
    ]
    system_config = config_dir / "fonts.conf"
    if system_config.is_file():
        lines.append(
            f'  <include ignore_missing="yes">{system_config.as_posix()}</include>'
        )
    lines.append(f"  <dir>{font_dir.as_posix()}</dir>")
    windows_fonts = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"
    lines.append(f"  <dir>{windows_fonts.as_posix()}</dir>")
    local_appdata = os.environ.get("LOCALAPPDATA")
    if local_appdata:
        user_fonts = Path(local_appdata) / "Microsoft" / "Windows" / "Fonts"
        lines.append(f"  <dir>{user_fonts.as_posix()}</dir>")
    lines.append("</fontconfig>")

    try:
        config.write_text("\n".join(lines) + "\n", encoding="utf-8")
    except OSError:
        return
    os.environ.setdefault("FONTCONFIG_FILE", config.as_posix())
    if config_dir.is_dir():
        os.environ.setdefault("FONTCONFIG_PATH", config_dir.as_posix())


def _configure_gtk_runtime() -> None:
    """Set GTK/GI environment variables for the frozen Windows bundle."""

    base = _bundle_dir()

    typelib_dirs = [base / "girepository-1.0", base / "gi_typelibs"]
    existing = os.environ.get("GI_TYPELIB_PATH", "")
    parts = [str(p) for p in typelib_dirs if p.is_dir()]
    if existing:
        parts.append(existing)
    if parts:
        os.environ["GI_TYPELIB_PATH"] = os.pathsep.join(parts)

    data_dir = base / "share"
    existing_data = os.environ.get("XDG_DATA_DIRS", "")
    data_parts = [str(data_dir)] if data_dir.is_dir() else []
    if existing_data:
        data_parts.append(existing_data)
    if data_parts:
        os.environ["XDG_DATA_DIRS"] = os.pathsep.join(data_parts)

    schemas_dir = base / "glib-2.0" / "schemas"
    if schemas_dir.is_dir():
        os.environ.setdefault("GSETTINGS_SCHEMA_DIR", str(schemas_dir))

    pixbuf_cache = base / "lib" / "gdk-pixbuf-2.0" / "2.10.0" / "loaders.cache"
    if pixbuf_cache.is_file():
        os.environ.setdefault("GDK_PIXBUF_MODULE_FILE", str(pixbuf_cache))
    else:
        for cache in base.rglob("loaders.cache"):
            os.environ.setdefault("GDK_PIXBUF_MODULE_FILE", str(cache))
            break

    os.environ.setdefault("GTK_DATA_PREFIX", str(base))
    os.environ.setdefault("GTK_EXE_PREFIX", str(base))


def main() -> int:
    _configure_gtk_runtime()
    _configure_cjk_font()
    from parley.__main__ import main as run

    return run()


if __name__ == "__main__":
    raise SystemExit(main())
