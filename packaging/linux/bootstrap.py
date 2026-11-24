#!/usr/bin/env python3
"""Create the private Python environment used by the Linux packages.

The .deb, .rpm and AppImage builds reuse the GTK 4 and PyGObject libraries from
the operating system and install the speech packages in
``~/.local/share/parley/venv`` on first start. This script shows a small GTK
window while that happens and writes the full output to
``~/.local/share/parley/logs/bootstrap.log``.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import queue
import subprocess
import sys
import threading
import time
import venv
from pathlib import Path

LOG_NAME = "bootstrap.log"
STAMP_NAME = ".parley-requirements"


def _log_path(venv_dir: Path) -> Path:
    return venv_dir.parent / "logs" / LOG_NAME


def _requirements_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _venv_python(venv_dir: Path) -> Path:
    if sys.platform == "win32":
        return venv_dir / "Scripts" / "python.exe"
    return venv_dir / "bin" / "python"


def _run(command: list[str], log, env: dict[str, str]) -> None:
    log.write(f"\n$ {' '.join(command)}\n")
    log.flush()
    process = subprocess.run(
        command,
        stdout=log,
        stderr=subprocess.STDOUT,
        env=env,
        check=False,
    )
    if process.returncode != 0:
        raise RuntimeError(
            f"Command failed with exit code {process.returncode}: {' '.join(command)}"
        )


def _has_pip(python: Path) -> bool:
    process = subprocess.run(
        [str(python), "-m", "pip", "--version"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return process.returncode == 0


def _ensure_pip(python: Path, log, env: dict[str, str]) -> list[str]:
    """Return a working pip command for the private environment.

    A previous start can leave a half-created environment without pip, so try
    the bundled ensurepip first and fall back to the system pip when needed.
    """

    if _has_pip(python):
        return [str(python), "-m", "pip"]

    log.write("\nRestoring pip inside the private environment\n")
    subprocess.run(
        [str(python), "-m", "ensurepip", "--upgrade"],
        stdout=log,
        stderr=subprocess.STDOUT,
        env=env,
        check=False,
    )
    if _has_pip(python):
        return [str(python), "-m", "pip"]

    system_pip = [sys.executable, "-m", "pip", "--python", str(python)]
    probe = subprocess.run(
        [*system_pip, "--version"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    if probe.returncode == 0:
        return system_pip

    raise RuntimeError(
        "pip is not available. Install the python3-pip package and run Parley again."
    )


def prepare(app_dir: Path, venv_dir: Path, requirements: Path) -> None:
    log_path = _log_path(venv_dir)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text("", encoding="utf-8")

    python = _venv_python(venv_dir)
    with log_path.open("a", encoding="utf-8") as log:
        log.write(f"Parley bootstrap {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        log.write(f"app: {app_dir}\nvenv: {venv_dir}\n")

        if not python.exists():
            log.write("\nCreating the private Python environment\n")
            builder = venv.EnvBuilder(
                system_site_packages=True,
                with_pip=True,
                clear=venv_dir.exists(),
            )
            builder.create(str(venv_dir))
        if not python.exists():
            raise RuntimeError("python was not created inside the environment")

        env = dict(os.environ)
        for name in ("PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV", "PIP_USER"):
            env.pop(name, None)
        env["PIP_DISABLE_PIP_VERSION_CHECK"] = "1"
        env["PIP_NO_INPUT"] = "1"

        pip = _ensure_pip(python, log, env)
        _run([*pip, "install", "--upgrade", "pip"], log, env)
        _run(
            [
                *pip,
                "install",
                "--upgrade",
                "--prefer-binary",
                "--no-warn-script-location",
                "-r",
                str(requirements),
            ],
            log,
            env,
        )

        stamp = venv_dir / STAMP_NAME
        stamp.write_text(_requirements_hash(requirements), encoding="utf-8")
        log.write("\nEnvironment ready\n")


def show_window(app_dir: Path, venv_dir: Path, requirements: Path) -> int:
    try:
        import gi

        gi.require_version("Gtk", "4.0")
        from gi.repository import GLib, Gtk
    except (ImportError, ValueError) as exc:
        print(f"Parley needs PyGObject and GTK 4: {exc}", file=sys.stderr)
        return 2

    Gtk.init()
    loop = GLib.MainLoop()

    window = Gtk.Window()
    window.set_title("Parley")
    window.set_default_size(560, 280)
    window.set_resizable(False)
    window.set_decorated(True)

    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
    box.set_margin_top(28)
    box.set_margin_bottom(28)
    box.set_margin_start(32)
    box.set_margin_end(32)

    heading = Gtk.Label(label="Preparing Parley")
    heading.set_xalign(0)
    heading.set_wrap(True)
    heading.add_css_class("title-2")

    description = Gtk.Label(
        label=(
            "Parley is installing the speech libraries it needs. This one-time "
            "step downloads a few hundred megabytes and needs an internet "
            "connection."
        )
    )
    description.set_xalign(0)
    description.set_wrap(True)

    progress = Gtk.ProgressBar()
    progress.set_pulse_step(0.08)

    detail = Gtk.Label(label="Starting…")
    detail.set_xalign(0)
    detail.set_wrap(True)
    detail.add_css_class("dim-label")

    close_button = Gtk.Button(label="Close")
    close_button.set_halign(Gtk.Align.END)
    close_button.set_visible(False)
    close_button.connect("clicked", lambda *_args: loop.quit())

    box.append(heading)
    box.append(description)
    box.append(progress)
    box.append(detail)
    box.append(close_button)
    window.set_child(box)

    provider = Gtk.CssProvider()
    provider.load_from_data(
        b"window { background: #f6f7fb; }"
        b"label.title-2 { font-size: 20pt; font-weight: 700; color: #1f2a44; }"
        b"label.dim-label { color: #5b6478; }"
        b"label.error { color: #b42318; }"
        b"progressbar trough { min-height: 8px; border-radius: 4px; }"
    )
    display = window.get_display()
    if display is not None:
        Gtk.StyleContext.add_provider_for_display(
            display, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

    results: queue.Queue[tuple[bool, str]] = queue.Queue()
    outcome = {"ok": False}
    started = time.monotonic()

    def worker() -> None:
        try:
            prepare(app_dir, venv_dir, requirements)
            results.put((True, ""))
        except Exception as exc:  # noqa: BLE001 - reported in the window and log
            results.put((False, str(exc)))

    def tick() -> bool:
        progress.pulse()
        elapsed = int(time.monotonic() - started)
        detail.set_label(
            f"Downloading and installing packages… {elapsed // 60}m {elapsed % 60:02d}s"
        )
        return True

    def poll() -> bool:
        try:
            ok, message = results.get_nowait()
        except queue.Empty:
            return True

        if ok:
            outcome["ok"] = True
            detail.set_label("Ready. Starting Parley…")
            progress.set_fraction(1.0)
            loop.quit()
            return False

        heading.set_label("Setup failed")
        description.set_label(
            "Parley could not install its speech libraries. Check the connection "
            "and try again."
        )
        detail.set_label(f"{message}\n\nLog: {_log_path(venv_dir)}")
        detail.add_css_class("error")
        progress.set_visible(False)
        close_button.set_visible(True)
        close_button.grab_focus()
        return False

    def on_close(*_args) -> bool:
        loop.quit()
        return False

    window.connect("close-request", on_close)
    window.connect("destroy", lambda *_args: loop.quit())
    GLib.timeout_add(120, tick)
    GLib.timeout_add(250, poll)
    threading.Thread(target=worker, daemon=True).start()

    window.present()
    loop.run()
    return 0 if outcome["ok"] else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app-dir", type=Path, required=True)
    parser.add_argument("--venv", type=Path, required=True)
    parser.add_argument("--requirements", type=Path, required=True)
    args = parser.parse_args(argv)

    venv_dir = args.venv.expanduser().resolve()
    venv_dir.parent.mkdir(parents=True, exist_ok=True)
    if args.requirements.exists() and (
        _venv_python(venv_dir).exists()
        and (venv_dir / STAMP_NAME).exists()
        and (venv_dir / STAMP_NAME).read_text(encoding="utf-8").strip()
        == _requirements_hash(args.requirements)
    ):
        return 0
    return show_window(
        args.app_dir.expanduser().resolve(),
        venv_dir,
        args.requirements.expanduser().resolve(),
    )


if __name__ == "__main__":
    raise SystemExit(main())
