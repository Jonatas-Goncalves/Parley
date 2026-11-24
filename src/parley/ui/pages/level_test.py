"""Guided level test: answer a few speaking prompts and see an estimate.

The test only listens. Each answer is transcribed locally, measured by the
speech recogniser and turned into the same personal 0-100 conversation score
used by Voice Practice. It is inspired by speaking tasks such as IELTS and
TOEFL, but it has no official value.
"""

from __future__ import annotations

import threading

import gi

gi.require_version("Gtk", "4.0")

from gi.repository import GLib, Gtk

from ...audio import Recorder
from ...audio.wave_io import write_wav
from ...core.config import AUDIO_DIR, ensure_directories
from ...core.scoring import (
    TurnMetrics,
    save_session,
    score_turns,
)
from ...core.stt import SpeechToText
from ..helpers import (
    button,
    card,
    horizontal,
    label,
    page_body,
    page_scroll,
)

STT = SpeechToText()

PROMPT_COUNT = 15


class LevelTestPage(Gtk.Box):
    def __init__(self, window, state) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.window = window
        self.state = state
        self._recorder: Recorder | None = None
        self._recording = False
        self._busy = False
        self._index = 0
        self._turns: list[TurnMetrics] = []
        self._finished = False
        self._closed = False

        body = page_body()
        body.append(label(state.t("level_test_title"), "hero-title", wrap=True))
        body.append(label(state.t("level_test_desc"), "muted", wrap=True))

        self.counter_label = label("", "card-title")
        self.prompt_label = label("", "section-title", wrap=True)
        body.append(self.counter_label)
        body.append(self.prompt_label)

        controls = horizontal(8)
        self.record_button = button(
            state.t("level_test_record"), "primary", self._toggle_record
        )
        self.retry_button = button(
            state.t("level_test_retry"), "ghost", self._restart
        )
        self.retry_button.set_visible(False)
        controls.append(self.record_button)
        controls.append(self.retry_button)
        body.append(controls)

        self.status_label = label("", "muted", wrap=True)
        body.append(self.status_label)

        outer, inner = card()
        self.result_score = label("", "score-big")
        self.result_level = label("", "card-title", wrap=True)
        self.result_detail = label("", "muted", wrap=True)
        inner.append(self.result_score)
        inner.append(self.result_level)
        inner.append(self.result_detail)
        self.result_card = outer
        self.result_card.set_visible(False)
        body.append(self.result_card)

        body.append(label(state.t("level_test_disclaimer"), "progress-note", wrap=True))
        self.append(page_scroll(body))

        self.connect("unrealize", self.shutdown)
        self._show_prompt()

    # -- prompt flow -----------------------------------------------------
    def _show_prompt(self) -> None:
        total = PROMPT_COUNT
        self.counter_label.set_label(
            self.state.t(
                "level_test_prompt_counter",
                current=min(self._index + 1, total),
                total=total,
            )
        )
        self.prompt_label.set_label(self.state.t(f"level_test_prompt_{self._index + 1}"))
        self.status_label.set_label("")
        self.record_button.set_label(self.state.t("level_test_record"))
        self.record_button.set_sensitive(True)
        self.record_button.remove_css_class("mic")
        self._recording = False
        self._busy = False

    def _toggle_record(self) -> None:
        if self._finished or self._busy:
            return
        recorder = self._ensure_recorder()
        if recorder is None:
            return
        if not self._recording:
            recorder.capture_start()
            self._recording = True
            self.record_button.set_label(self.state.t("level_test_stop"))
            self.record_button.add_css_class("mic")
            self.status_label.set_label(self.state.t("listening"))
            return

        audio = recorder.capture_stop()
        self._recording = False
        self.record_button.remove_css_class("mic")
        self.record_button.set_sensitive(False)
        self._busy = True
        if audio.size == 0:
            self.status_label.set_label(self.state.t("error_mic", error="no audio"))
            self._busy = False
            self.record_button.set_sensitive(True)
            return
        self._transcribe(audio)

    def _ensure_recorder(self) -> Recorder | None:
        if self._recorder is None:
            self._recorder = Recorder()
        if not self._recorder.running:
            try:
                self._recorder.start()
            except Exception as exc:
                self.status_label.set_label(
                    self.state.t("error_mic", error=str(exc))
                )
                return None
        return self._recorder

    def _transcribe(self, audio) -> None:
        ensure_directories()
        self.status_label.set_label(self.state.t("level_test_thinking"))
        path = AUDIO_DIR / f"level-test-{self._index + 1}.wav"
        write_wav(path, audio)
        language = self.state.target
        model_name = self.state.whisper_model

        def worker() -> None:
            try:
                result = STT.transcribe(path, model_name, language)
            except Exception as exc:
                GLib.idle_add(self._show_error, str(exc))
                return
            GLib.idle_add(self._accept_answer, result)

        threading.Thread(target=worker, name="parley-level-test", daemon=True).start()

    def _show_error(self, message: str) -> bool:
        if self._closed:
            return False
        self.status_label.set_label(self.state.t("error_generic", error=message))
        self._busy = False
        self.record_button.set_sensitive(True)
        self.record_button.set_label(self.state.t("level_test_record"))
        return False

    def _accept_answer(self, result) -> bool:
        if self._closed:
            return False
        spoken = (result.text or "").strip()
        self._turns.append(
            TurnMetrics(
                text=spoken,
                words=int(result.words or len(spoken.split())),
                speech_seconds=float(result.speech_duration or 0.0),
                pause_ratio=float(result.pause_ratio or 0.0),
                words_per_minute=float(result.words_per_minute or 0.0),
                confidence=float(result.confidence or 0.8),
            )
        )
        self._index += 1
        if self._index >= PROMPT_COUNT:
            self._finish()
        else:
            self._busy = False
            self._show_prompt()
        return False

    # -- result ----------------------------------------------------------
    def _finish(self) -> None:
        self._finished = True
        self._busy = False
        self._recording = False
        result = score_turns(self._turns)
        save_session(
            self.state.target,
            "level_test",
            self.state.t("level_test_title"),
            result,
            mode="level_test",
        )

        self.counter_label.set_label(self.state.t("level_test_done"))
        self.prompt_label.set_label(
            self.state.t(
                "level_test_result",
                score=result.score,
                level=self.state.t(result.band_key),
            )
        )
        self.status_label.set_label("")
        self.record_button.set_visible(False)
        self.retry_button.set_visible(True)

        self.result_score.set_label(f"{result.score}/100")
        band = self.state.t(result.band_key)
        self.result_level.set_label(band)
        self.result_detail.set_label(
            self.state.t(
                "session_score_body",
                score=result.score,
                level=band,
                turns=result.turns,
                words=result.words,
            )
            + "\n"
            + self.state.t("progress_desc")
        )
        self.result_card.set_visible(True)

    def _restart(self) -> None:
        self._index = 0
        self._turns = []
        self._finished = False
        self.result_card.set_visible(False)
        self.record_button.set_visible(True)
        self.retry_button.set_visible(False)
        self._show_prompt()

    # -- lifecycle -------------------------------------------------------
    def shutdown(self, *_args) -> None:
        self._closed = True
        if self._recorder is not None:
            try:
                self._recorder.stop()
            except Exception:
                pass
            self._recorder = None
        self._recording = False
