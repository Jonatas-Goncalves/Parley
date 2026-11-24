"""Practice hub: conversation, pronunciation and supplements."""

from __future__ import annotations

from datetime import datetime

import gi

gi.require_version("Gtk", "4.0")

from gi.repository import Gtk

from ...core import scoring
from ...core.config import language_choice_label
from ..helpers import (
    button,
    card,
    horizontal,
    label,
    page_body,
    page_scroll,
    vertical,
)


def _short_date(raw: str) -> str:
    try:
        return datetime.fromisoformat(str(raw).replace("Z", "+00:00")).astimezone().strftime("%Y-%m-%d")
    except (TypeError, ValueError):
        return str(raw)[:10]


class PracticePage(Gtk.Box):
    def __init__(self, window, state) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.window = window
        self.state = state

        body = page_body()
        body.append(label(state.t("practice_title"), "hero-title", wrap=True))
        body.append(label(state.t("voice_practice"), "section-title"))

        body.append(
            self._mode_card(
                "voice_practice",
                "voice_practice_desc",
                "session",
            )
        )
        body.append(
            self._mode_card(
                "pronunciation",
                "pronunciation_desc",
                "pronunciation",
            )
        )

        body.append(label(state.t("supplements"), "section-title"))
        body.append(self._supplement_card())
        body.append(self._progress_card())

        self.append(page_scroll(body))

    def _levels(self, mode: str) -> Gtk.Box:
        row = horizontal(10)
        for band in ("beginner", "intermediate", "advanced"):
            row.append(
                button(
                    self.state.t(band),
                    "scenario",
                    lambda band=band, mode=mode: self.window.show_page(
                        "scenarios", mode=mode, band=band
                    ),
                )
            )
        return row

    def _mode_card(self, title_key: str, subtitle_key: str, mode: str) -> Gtk.Box:
        outer, inner = card(self.state.t(title_key), self.state.t(subtitle_key))
        inner.append(self._levels(mode if mode != "session" else "voice_practice"))
        return outer

    def _supplement_card(self) -> Gtk.Box:
        outer, inner = card()
        stories = horizontal(10)
        text = vertical(2)
        text.append(label(self.state.t("spoken_stories"), "card-title"))
        text.append(label(self.state.t("spoken_stories_desc"), "card-subtitle", wrap=True))
        text.set_hexpand(True)
        stories.append(text)
        stories.append(button("▶", "ghost", lambda: self.window.show_page("stories")))
        inner.append(stories)

        sentence = horizontal(10)
        text = vertical(2)
        text.append(label(self.state.t("complete_sentence"), "card-title"))
        text.append(label(self.state.t("complete_sentence_desc"), "card-subtitle", wrap=True))
        text.set_hexpand(True)
        sentence.append(text)
        sentence.append(button("✎", "ghost", lambda: self.window.show_page("sentence")))
        inner.append(sentence)
        return outer

    def _progress_card(self) -> Gtk.Box:
        outer, inner = card(
            self.state.t("progress_title"),
            self.state.t("progress_desc"),
        )
        history = scoring.load_history()
        current = scoring.history_for_language(history, self.state.target)
        summary = scoring.summarize(current)
        language_name = language_choice_label(self.state.target)

        if not current:
            inner.append(
                label(
                    self.state.t("progress_empty", language=language_name),
                    "muted",
                    wrap=True,
                )
            )
        else:
            inner.append(
                label(
                    self.state.t(
                        "progress_sessions",
                        count=summary["count"],
                        average=summary["average"],
                        best=summary["best"],
                    ),
                    "card-title",
                    wrap=True,
                )
            )
            inner.append(
                label(
                    self.state.t(
                        "progress_level",
                        level=self.state.t(summary["band_key"]),
                    ),
                    "muted",
                    wrap=True,
                )
            )
            inner.append(label(self.state.t("progress_recent"), "card-title"))
            for record in reversed(current[-5:]):
                row = horizontal(10)
                row.append(label(_short_date(record.get("date", "")), "muted"))
                title = str(record.get("scenario_label") or record.get("scenario") or "")
                text = label(title, wrap=True)
                text.set_hexpand(True)
                row.append(text)
                row.append(label(f"{int(record.get('score') or 0)}/100", "card-title"))
                inner.append(row)

        grouped = scoring.languages_with_history(history)
        if len(grouped) > 1:
            inner.append(label(self.state.t("progress_overall"), "card-title"))
            for language, data in sorted(grouped.items()):
                inner.append(
                    label(
                        self.state.t(
                            "progress_language_row",
                            language=language_choice_label(language),
                            count=data["count"],
                            average=data["average"],
                        ),
                        "muted",
                        wrap=True,
                    )
                )

        actions = horizontal(8)
        actions.append(
            button(
                self.state.t("progress_level_test"),
                "primary",
                lambda: self.window.show_page("level_test"),
            )
        )
        inner.append(actions)
        return outer
