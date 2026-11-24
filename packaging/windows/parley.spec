# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller definition for the Windows build.

The GTK 4 runtime comes from conda-forge. Its DLLs, typelibs, GSettings schemas,
icon themes and gdk-pixbuf loaders are copied next to Parley.exe; the entry point
sets the matching environment variables before importing gi.
"""

import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_data_files

PROJECT = Path(SPECPATH).resolve().parents[1]
PREFIX = Path(sys.prefix)
LIBRARY = PREFIX / "Library"

# collect_data_files() imports the package, so make the source tree importable
# before the spec is evaluated.
SRC = PROJECT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

datas = []
binaries = []
hiddenimports = [
    "gi",
    "gi.repository.Gtk",
    "gi.repository.Gdk",
    "gi.repository.Gio",
    "gi.repository.GLib",
    "gi.repository.GObject",
    "gi.repository.Pango",
    "gi.repository.GdkPixbuf",
]

datas += collect_data_files("parley", includes=["ui/*.css", "content/*.json"])

cacert = PROJECT / "assets" / "cacert.pem"
if cacert.exists():
    datas.append((str(cacert), "assets"))

cjk_fonts = PROJECT / "assets" / "fonts" / "noto-cjk"
if cjk_fonts.is_dir():
    datas.append((str(cjk_fonts), "share/fonts/noto-cjk"))

for package in (
    "faster_whisper",
    "ctranslate2",
    "onnxruntime",
    "av",
    "tokenizers",
    "huggingface_hub",
    "sounddevice",
    "soundfile",
    "piper",
):
    try:
        package_datas, package_binaries, package_hidden = collect_all(package)
    except Exception:
        continue
    datas += package_datas
    binaries += package_binaries
    hiddenimports += package_hidden

if LIBRARY.is_dir():
    for dll in sorted((LIBRARY / "bin").glob("*.dll")):
        binaries.append((str(dll), "."))

    for name in (
        "gdk-pixbuf-query-loaders.exe",
        "gspawn-win64-helper.exe",
        "gdbus.exe",
    ):
        helper = LIBRARY / "bin" / name
        if helper.exists():
            binaries.append((str(helper), "."))

    runtime_dirs = {
        LIBRARY / "lib" / "girepository-1.0": "girepository-1.0",
        LIBRARY / "share" / "glib-2.0" / "schemas": "glib-2.0/schemas",
        LIBRARY / "share" / "icons": "share/icons",
        LIBRARY / "share" / "themes": "share/themes",
        LIBRARY / "etc" / "gtk-4.0": "etc/gtk-4.0",
        LIBRARY / "etc" / "fonts": "etc/fonts",
    }
    for source, destination in runtime_dirs.items():
        if source.is_dir():
            datas.append((str(source), destination))

icon = PROJECT / "assets" / "icons" / "parley.ico"

a = Analysis(
    [str(PROJECT / "packaging" / "windows" / "launcher.py")],
    pathex=[str(PROJECT / "src")],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "pytest", "IPython", "matplotlib"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Parley",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    icon=str(icon) if icon.exists() else None,
)

collect = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="Parley",
)
