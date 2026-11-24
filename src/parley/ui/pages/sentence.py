"""Complete the Sentence: listen to a short text and fill the blanks."""

from __future__ import annotations

import html
import threading

import gi

gi.require_version("Gtk", "4.0")

from gi.repository import GLib, Gtk

from ...core.config import (
    default_voice_for_language,
    voice_config_path,
    voice_model_path,
)
from ...core.exercises import check_cloze, generate_text, make_cloze
from ...core.scenarios import get_scenario
from ...core.tts import PiperTTS
from ..helpers import (
    button,
    card,
    horizontal,
    label,
    muted_markup,
    page_body,
    page_scroll,
    vertical,
    word_markup,
)
from ..widgets.audio_bar import AudioBar

TTS = PiperTTS()


class SentencePage(Gtk.Box):
    def __init__(self, window, state) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.window = window
        self.state = state
        self.full_text = ""
        self.masked_text = ""
        self.answers: list[str] = []
        self.entries: list[Gtk.Entry] = []
        self._audio_path = None
        self._generating = False

        body = page_body()
        body.append(label(state.t("complete_sentence"), "hero-title", wrap=True))
        body.append(label(state.t("listen_and_fill"), "section-title", wrap=True))
        body.append(label(state.t("complete_sentence_desc"), "muted", wrap=True))

        self.audio = AudioBar()
        body.append(self.audio)

        outer, inner = card()
        self.text_label = label(state.t("loading"), "card-title", wrap=True, markup=True)
        inner.append(self.text_label)
        self.entries_box = vertical(8)
        inner.append(self.entries_box)
        self.banner = label("", "muted", wrap=True)
        inner.append(self.banner)
        body.append(outer)

        actions = horizontal(8)
        self.finish_button = button(state.t("finish"), "primary", self._finish)
        self.finish_button.set_sensitive(False)
        actions.append(self.finish_button)
        actions.append(button("↻  " + state.t("new_exercise"), "ghost", self._generate))
        body.append(actions)

        self.append(page_scroll(body))
        GLib.idle_add(self._generate)

    def shutdown(self) -> None:
        self.audio.stop()

    # -- generation ------------------------------------------------------
    def _generate(self) -> None:
        if self._generating:
            return
        if self.state.snapshot().state != "running":
            self.banner.set_text(self.state.t("ai_not_ready"))
            self.state.start_runtime()
            self.state.watch_runtime(self._on_snapshot)
            return
        self._generating = True
        self.banner.set_text(self.state.t("loading"))
        self.text_label.set_markup(self.state.t("loading"))
        self.finish_button.set_sensitive(False)
        self._clear_entries()
        snapshot = self.state.snapshot()
        scenario = get_scenario(str(self.state.config.get("scenario") or "daily_routine"))

        def worker() -> None:
            try:
                text = generate_text(
                    scenario,
                    self.state.target,
                    scenario.level,
                    4,
                    self.state.backend,
                    snapshot.base_url or self.state.base_url,
                    snapshot.model or self.state.model,
                )
            except Exception as exc:
                GLib.idle_add(self._failed, str(exc))
                return
            GLib.idle_add(self._ready, text)

        threading.Thread(target=worker, name="parley-cloze", daemon=True).start()

    def _on_snapshot(self, snapshot) -> None:
        if snapshot.state == "running":
            self._generate()
        elif snapshot.state == "error":
            self.text_label.set_markup("")
            self.banner.set_text(
                self.state.t("error_backend", error=snapshot.error or snapshot.message)
            )

    def _failed(self, message: str) -> bool:
        self._generating = False
        self.text_label.set_markup("")
        self.banner.set_text(self.state.t("error_generic", error=message))
        return False

    def _ready(self, text: str) -> bool:
        self._generating = False
        self.full_text = (text or "").strip()
        self.masked_text, self.answers = make_cloze(self.full_text, count=6)
        if not self.answers:
            self.banner.set_text(self.state.t("error_generic", error="no blanks"))
            return False

        parts = self.masked_text.split("____")
        display = []
        for index, part in enumerate(parts[:-1]):
            display.append(html.escape(part))
            display.append(f"<b>({index + 1})</b> ____")
        display.append(html.escape(parts[-1]))
        self.text_label.set_markup("".join(display))

        self._clear_entries()
        for index, _answer in enumerate(self.answers):
            row = horizontal(8)
            number = label(f"{index + 1}.", "muted")
            number.set_size_request(24, -1)
            entry = Gtk.Entry()
            entry.set_hexpand(True)
            entry.add_css_class("answer-entry")
            entry.set_placeholder_text("…")
            entry.connect("activate", self._focus_next, index)
            self.entries.append(entry)
            row.append(number)
            row.append(entry)
            self.entries_box.append(row)

        self.finish_button.set_sensitive(True)
        self.banner.set_text("")
        self._synthesize()
        return False

    def _focus_next(self, _entry, index: int) -> None:
        if index + 1 < len(self.entries):
            self.entries[index + 1].grab_focus()

    def _clear_entries(self) -> None:
        while True:
            child = self.entries_box.get_first_child()
            if child is None:
                break
            self.entries_box.remove(child)
        self.entries = []

    # -- audio -----------------------------------------------------------
    def _synthesize(self) -> None:
        voice = default_voice_for_language(self.state.target)
        if not (voice_model_path(voice).exists() and voice_config_path(voice).exists()):
            self.banner.set_text(self.state.t("error_voice"))
            return
        text = self.full_text

        def worker() -> None:
            try:
                path = TTS.synthesize_plain(text, voice, self.state.target)
            except Exception as exc:
                GLib.idle_add(self._failed, str(exc))
                return
            if path:
                GLib.idle_add(self._load_audio, str(path))

        threading.Thread(target=worker, name="parley-cloze-tts", daemon=True).start()

    def _load_audio(self, path: str) -> bool:
        self._audio_path = path
        self.audio.load(path)
        return False

    # -- checking --------------------------------------------------------
    def _finish(self) -> None:
        if not self.answers:
            return
        values = [entry.get_text().strip() for entry in self.entries]
        results = check_cloze(self.answers, values)
        parts = self.masked_text.split("____")
        chunks = []
        correct = 0
        for index, part in enumerate(parts[:-1]):
            chunks.append(html.escape(part))
            given = values[index] if index < len(values) else ""
            expected = self.answers[index] if index < len(self.answers) else ""
            if results[index]:
                correct += 1
                chunks.append(word_markup(self.text_label, expected, True))
            else:
                chunks.append(word_markup(self.text_label, given or "—", False))
                chunks.append(" ")
                chunks.append(muted_markup(self.text_label, f"({expected})"))
        chunks.append(html.escape(parts[-1]))
        self.text_label.set_markup("".join(chunks))
        self.banner.set_label(
            self.state.t("bullets", correct=correct, wrong=len(results) - correct)
        )
