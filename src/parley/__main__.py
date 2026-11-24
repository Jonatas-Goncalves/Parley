"""Run Parley from a source checkout, a package or a frozen build."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent
SOURCE_ROOT = PACKAGE_DIR.parent.parent
if (SOURCE_ROOT / "src" / "parley").is_dir() and str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from . import __version__  # noqa: E402 - the package path is prepared first

HELP_TEXT = """\
Usage: parley [options]

Parley is a local, voice-first language tutor.

Options:
  -h, --help       Show this help and exit
  -V, --version    Show the version and exit
  --debug          Print diagnostics and enable verbose logs
  --debug-info     Print diagnostics and exit

The interface starts when no option is given. Story audio can be read from a
checkout during development with PARLEY_STORIES_DIR=/path/to/assets/stories.
"""


def _stderr(message: str) -> None:
    stream = sys.stderr or sys.stdout
    if stream is not None:
        print(message, file=stream)


def _frozen_base() -> Path | None:
    if not getattr(sys, "frozen", False):
        return None
    return Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))


def _configure_frozen_runtime(base: Path) -> None:
    """Point GTK at the runtime files that PyInstaller copied next to the app."""

    os.environ["PATH"] = str(base) + os.pathsep + os.environ.get("PATH", "")

    typelibs = base / "girepository-1.0"
    if typelibs.is_dir():
        os.environ.setdefault("GI_TYPELIB_PATH", str(typelibs))

    schemas = base / "glib-2.0" / "schemas"
    if schemas.is_dir():
        os.environ.setdefault("GSETTINGS_SCHEMA_DIR", str(schemas))

    os.environ.setdefault("GTK_DATA_PREFIX", str(base))
    os.environ.setdefault("GTK_EXE_PREFIX", str(base))
    os.environ.setdefault("GTK_THEME", "Adwaita")

    # The gdk-pixbuf loader cache contains absolute DLL paths, so it is built
    # once per installation in a writable folder instead of at packaging time.
    cache_dir = Path(
        os.environ.get("LOCALAPPDATA") or tempfile.gettempdir()
    ) / "Parley"
    cache = cache_dir / "loaders.cache"
    query = base / "gdk-pixbuf-query-loaders.exe"
    if query.exists() and not cache.exists():
        try:
            cache_dir.mkdir(parents=True, exist_ok=True)
            modules = sorted(base.glob("libpixbufloader-*.dll"))
            if modules:
                result = subprocess.run(
                    [str(query), *(str(module) for module in modules)],
                    capture_output=True,
                    text=True,
                    timeout=60,
                    check=False,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
                if result.returncode == 0 and result.stdout.strip():
                    cache.write_text(result.stdout, encoding="utf-8")
        except Exception:
            pass
    if cache.exists():
        os.environ.setdefault("GDK_PIXBUF_MODULE_FILE", str(cache))

    bundled_ca = base / "assets" / "cacert.pem"
    if bundled_ca.exists():
        os.environ.setdefault("SSL_CERT_FILE", str(bundled_ca))
        os.environ.setdefault("REQUESTS_CA_BUNDLE", str(bundled_ca))
        os.environ.setdefault("CURL_CA_BUNDLE", str(bundled_ca))


def _configure_ca_bundle() -> None:
    """Use the bundled CA file only when the system has no trust store."""

    system_ca = (
        Path("/etc/ssl/ca-bundle.pem"),
        Path("/var/lib/ca-certificates/ca-bundle.pem"),
    )
    if any(path.exists() for path in system_ca):
        return
    bundled = SOURCE_ROOT / "assets" / "cacert.pem"
    if bundled.exists():
        os.environ.setdefault("SSL_CERT_FILE", str(bundled))
        os.environ.setdefault("REQUESTS_CA_BUNDLE", str(bundled))
        os.environ.setdefault("CURL_CA_BUNDLE", str(bundled))


base = _frozen_base()
if base is not None:
    _configure_frozen_runtime(base)
else:
    _configure_ca_bundle()


def _diagnostics() -> None:
    """Print the details that help when a local installation does not start."""

    import platform

    from .core.config import DATA_DIR

    print(f"Parley {__version__}")
    print(f"Python {platform.python_version()} ({sys.executable})")
    print(f"System {platform.system()} {platform.release()} ({platform.machine()})")
    print(f"Data directory: {DATA_DIR}")
    print(f"Stories directory: {os.environ.get('PARLEY_STORIES_DIR', DATA_DIR / 'stories')}")
    print(f"Stories URL: {os.environ.get('PARLEY_STORIES_URL', 'default')}")
    try:
        import gi

        gi.require_version("Gtk", "4.0")
        from gi.repository import GLib, Gtk

        print(f"PyGObject {gi.__version__}")
        print(f"GTK {Gtk.get_major_version()}.{Gtk.get_minor_version()}.{Gtk.get_micro_version()}")
        print(f"GLib {GLib.MAJOR_VERSION}.{GLib.MINOR_VERSION}.{GLib.MICRO_VERSION}")
    except (ImportError, ValueError) as exc:
        print(f"GTK 4 is not available: {exc}")


def main() -> int:
    args: list[str] = []
    debug = False
    for argument in sys.argv[1:]:
        if argument in ("-h", "--help", "help"):
            print(HELP_TEXT, end="")
            return 0
        if argument in ("-V", "--version", "version"):
            print(f"Parley {__version__}")
            return 0
        if argument == "--debug-info":
            _diagnostics()
            return 0
        if argument == "--debug":
            debug = True
            continue
        args.append(argument)

    if debug:
        os.environ["PARLEY_DEBUG"] = "1"
        import logging

        logging.basicConfig(
            level=logging.DEBUG,
            format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        )
        _diagnostics()

    try:
        from .application import main as run
    except ModuleNotFoundError as exc:
        _stderr(
            "Parley could not start because a dependency is missing: "
            f"{exc.name}.\n"
            "Install the system packages listed in docs/install-linux.md or "
            "docs/install-windows.md, then run again."
        )
        return 1
    return run([sys.argv[0], *args])


if __name__ == "__main__":
    raise SystemExit(main())
