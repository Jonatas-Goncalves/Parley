"""GTK application entry point."""

from __future__ import annotations

from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")

from gi.repository import Gdk, Gio, Gtk

from .ui.state import AppState, detect_system_theme
from .ui.window import ParleyWindow

APP_ID = "io.github.jonatasgoncalves.Parley"

_CSS_PROVIDER: Gtk.CssProvider | None = None


def _load_css(theme: str = "system") -> None:
    """Load the palette for ``theme`` followed by the shared stylesheet.

    ``theme`` may be ``system``, ``light`` or ``dark``. In system mode the
    desktop colour scheme is detected and the GTK settings are left untouched,
    so a later desktop change can be followed without a restart.
    """

    global _CSS_PROVIDER

    mode = theme if theme in ("system", "light", "dark") else "system"
    theme_name = detect_system_theme() if mode == "system" else mode
    folder = Path(__file__).with_name("ui")
    parts: list[str] = []
    for filename in (f"theme-{theme_name}.css", "style.css"):
        try:
            parts.append((folder / filename).read_text(encoding="utf-8"))
        except OSError:
            continue
    if not parts:
        return

    settings = Gtk.Settings.get_default()
    if settings is not None and mode in ("light", "dark"):
        scheme = getattr(Gtk, "InterfaceColorScheme", None)
        if (
            scheme is not None
            and settings.find_property("gtk-interface-color-scheme") is not None
        ):
            settings.set_property(
                "gtk-interface-color-scheme",
                scheme.DARK if theme_name == "dark" else scheme.LIGHT,
            )
        else:
            settings.set_property(
                "gtk-application-prefer-dark-theme", theme_name == "dark"
            )

    display = Gdk.Display.get_default()
    if display is None:
        return
    if _CSS_PROVIDER is not None:
        Gtk.StyleContext.remove_provider_for_display(display, _CSS_PROVIDER)
    provider = Gtk.CssProvider()
    provider.load_from_data("\n".join(parts).encode("utf-8"))
    Gtk.StyleContext.add_provider_for_display(
        display, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
    )
    _CSS_PROVIDER = provider


class ParleyApplication(Gtk.Application):
    def __init__(self) -> None:
        super().__init__(
            application_id=APP_ID,
            flags=Gio.ApplicationFlags.DEFAULT_FLAGS,
        )
        self.state = AppState()
        self.window: ParleyWindow | None = None

    def do_startup(self) -> None:
        Gtk.Application.do_startup(self)
        Gtk.Window.set_default_icon_name(APP_ID)
        _load_css(self.state.theme_mode)
        self._watch_system_theme()

    def _watch_system_theme(self) -> None:
        settings = Gtk.Settings.get_default()
        if settings is None:
            return
        for prop in (
            "gtk-interface-color-scheme",
            "gtk-application-prefer-dark-theme",
        ):
            if settings.find_property(prop) is not None:
                settings.connect(f"notify::{prop}", self._system_theme_changed)

    def _system_theme_changed(self, *_args) -> None:
        # Only follow the desktop when the user did not choose a fixed theme.
        if self.state.theme_mode == "system":
            self.apply_theme()

    def apply_theme(self) -> None:
        _load_css(self.state.theme_mode)

    def do_activate(self) -> None:
        if self.window is None:
            self.window = ParleyWindow(self, self.state)
        self.window.present()
        if not self.state.bool("onboarding_done", False):
            self.window.show_page("onboarding", push_history=False)
        else:
            self.window.show_page("welcome", push_history=False)
            self.state.start_runtime()
        self.window.connect("close-request", self._on_close)

    def _on_close(self, *_args) -> bool:
        if self.window is not None:
            self.window.shutdown()
        return False


def main(argv: list[str] | None = None) -> int:
    app = ParleyApplication()
    return app.run(argv)
