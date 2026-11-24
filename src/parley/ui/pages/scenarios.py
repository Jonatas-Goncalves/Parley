"""Scenario picker for conversation and pronunciation."""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")

from gi.repository import Gtk

from ...core.scenarios import scenarios_for_band
from ..helpers import (
    button,
    horizontal,
    label,
    page_body,
    page_scroll,
    vertical,
)


class ScenariosPage(Gtk.Box):
    def __init__(self, window, state, mode: str = "voice_practice", band: str = "beginner") -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.window = window
        self.state = state
        self.mode = mode
        self.band = band

        body = page_body()
        title = state.t("voice_practice" if mode == "voice_practice" else "pronunciation")
        body.append(label(title, "hero-title", wrap=True))

        heading = horizontal(10)
        heading.append(label(state.t(band), f"pill pill-{band}"))
        body.append(heading)

        body.append(label(state.t("what_topic"), "section-title"))
        if mode != "voice_practice":
            body.append(label(state.t("pronunciation_hint"), "muted", wrap=True))

        listing = vertical(8)
        for scenario in scenarios_for_band(band):
            listing.append(
                button(
                    scenario.label,
                    "scenario",
                    lambda scenario=scenario: self._open(scenario.id),
                )
            )
        body.append(listing)
        self.append(page_scroll(body))

    def _open(self, scenario_id: str) -> None:
        self.state.save(scenario=scenario_id)
        if self.mode == "voice_practice":
            self.window.show_page(
                "session",
                scenario_id=scenario_id,
                band=self.band,
            )
        else:
            self.window.show_page(
                "pronunciation",
                scenario_id=scenario_id,
                band=self.band,
            )
