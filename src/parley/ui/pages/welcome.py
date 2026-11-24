"""Welcome page: choose the language to practice."""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")

from gi.repository import Gtk

from ...core.config import SUPPORTED_LANGUAGES
from ..helpers import (
    FLAGS,
    button,
    horizontal,
    label,
    language_button_label,
    page_body,
    page_scroll,
)

ORDER = ("pt", "en", "es", "fr", "it", "ja", "ko", "zh")

TRANSLATED_LANGUAGES = {
    "ja": "language_ja",
    "ko": "language_ko",
    "zh": "language_zh",
}


class WelcomePage(Gtk.Box):
    def __init__(self, window, state) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.window = window
        self.state = state

        body = page_body()
        body.set_halign(Gtk.Align.CENTER)
        body.append(label(state.t("welcome_title"), "welcome-title", align=Gtk.Align.CENTER))
        body.append(label(state.t("welcome_prompt"), "welcome-subtitle", align=Gtk.Align.CENTER))
        body.append(self._language_grid())
        body.append(self._settings_row())
        body.set_valign(Gtk.Align.CENTER)
        self.append(page_scroll(body, max_width=720))

    def _language_grid(self) -> Gtk.Grid:
        grid = Gtk.Grid()
        grid.set_row_spacing(8)
        grid.set_column_spacing(8)
        grid.set_halign(Gtk.Align.CENTER)
        grid.add_css_class("lang-grid")
        codes = [code for code in ORDER if code in SUPPORTED_LANGUAGES]
        for index, code in enumerate(codes):
            widget = button(
                self._language_label(code),
                "lang-button",
                lambda code=code: self._choose(code),
            )
            widget.set_hexpand(True)
            if code == self.state.target:
                widget.add_css_class("active")
            grid.attach(widget, index % 2, index // 2, 1, 1)
        return grid

    def _settings_row(self) -> Gtk.Box:
        row = horizontal(8)
        row.set_halign(Gtk.Align.CENTER)
        row.set_margin_top(18)
        row.append(button("⚙  " + self.state.t("settings"), "ghost", self.window.open_settings))
        return row

    def _language_label(self, code: str) -> str:
        key = TRANSLATED_LANGUAGES.get(code)
        if key:
            name = self.state.t(key)
            return f"{FLAGS.get(code, '🌐')}  {name}"
        return language_button_label(code)

    def _choose(self, code: str) -> None:
        native = self.state.native
        if code == native:
            native = "pt" if code != "pt" else "en"
        self.state.save(target=code, native=native)
        self.window.show_page("practice")
