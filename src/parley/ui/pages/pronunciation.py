"""Pronunciation practice: read a phrase and compare the transcription."""

from __future__ import annotations

import threading

import gi

gi.require_version("Gtk", "4.0")

from gi.repository import GLib, Gtk

from ...audio import AudioPlayer, Recorder, play_blocking
from ...audio.wave_io import write_wav
from ...core.config import (
    AUDIO_DIR,
    default_voice_for_language,
    ensure_directories,
    voice_config_path,
    voice_model_path,
)
from ...core.exercises import (
    compare_reading,
    generate_text,
)
from ...core.scenarios import get_scenario
from ...core.stt import SpeechToText
from ...core.tts import PiperTTS
from ..helpers import (
    button,
    card,
    horizontal,
    label,
    page_body,
    page_scroll,
    word_markup,
)

STT = SpeechToText()
TTS = PiperTTS()


class PronunciationPage(Gtk.Box):
    def __init__(self, window, state, scenario_id: str = "meeting_someone_new", band: str = "beginner") -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.window = window
        self.state = state
        self.scenario = get_scenario(scenario_id)
        self.band = band
        self.phrase = ""
        self._recorder: Recorder | None = None
        self._recording = False
        self._player = AudioPlayer()

        body = page_body()
        body.append(label(self.scenario.label, "hero-title", wrap=True))
        meta = horizontal(8)
        meta.append(label(state.t(band), f"pill pill-{band}"))
        meta.append(label(state.t("pronunciation"), "muted"))
        body.append(meta)
        body.append(label(state.t("pronunciation_hint"), "muted", wrap=True))

        outer, inner = card()
        self.phrase_label = label(state.t("loading"), "card-title", wrap=True)
        inner.append(self.phrase_label)
        controls = horizontal(8)
        self.listen_button = button("🔊  " + state.t("play_audio"), "ghost", self._listen)
        self.record_button = button("🎙  " + state.t("your_turn"), "primary", self._toggle_record)
        self.next_button = button("↻  " + state.t("new_exercise"), "ghost", self._generate)
        controls.append(self.listen_button)
        controls.append(self.record_button)
        controls.append(self.next_button)
        inner.append(controls)
        body.append(outer)

        outer, inner = card()
        self.score_label = label("", "score-big")
        self.result_label = label("", wrap=True, markup=True)
        self.heard_label = label("", "muted", wrap=True)
        inner.append(self.score_label)
        inner.append(self.result_label)
        inner.append(self.heard_label)
        body.append(outer)

        self.banner = label("", "muted", wrap=True)
        body.append(self.banner)
        self.append(page_scroll(body))

        self.connect("unrealize", self.shutdown)
        GLib.idle_add(self._boot)

    # -- backend ---------------------------------------------------------
    def _boot(self) -> bool:
        snapshot = self.state.snapshot()
        if snapshot.state == "running":
            self.banner.set_text("")
            self._generate()
        else:
            self.banner.set_text(self.state.t("ai_not_ready"))
            self.state.start_runtime()
            self.state.watch_runtime(self._on_snapshot)
        return False

    def _on_snapshot(self, snapshot) -> None:
        if snapshot.state == "running":
            self.banner.set_text("")
            if not self.phrase:
                self._generate()
            return
        if snapshot.state == "error":
            self.banner.set_text(
                self.state.t("error_backend", error=snapshot.error or snapshot.message)
            )
            return
        self.banner.set_text(f"{snapshot.message or self.state.t('ai_not_ready')} ({snapshot.percent}%)")

    # -- phrase ----------------------------------------------------------
    def _generate(self) -> None:
        if self.state.snapshot().state != "running":
            self._boot()
            return
        self.phrase_label.set_label(self.state.t("loading"))
        self.score_label.set_label("")
        self.result_label.set_label("")
        self.heard_label.set_label("")
        snapshot = self.state.snapshot()

        def worker() -> None:
            try:
                text = generate_text(
                    self.scenario,
                    self.state.target,
                    self.scenario.level,
                    1,
                    self.state.backend,
                    snapshot.base_url or self.state.base_url,
                    snapshot.model or self.state.model,
                    max_words=18,
                )
            except Exception as exc:
                GLib.idle_add(self._show_error, str(exc))
                return
            GLib.idle_add(self._set_phrase, text)

        threading.Thread(target=worker, name="parley-phrase", daemon=True).start()

    def _set_phrase(self, text: str) -> bool:
        self.phrase = (text or "").strip().strip('"')
        self.phrase_label.set_label(self.phrase or self.state.t("error_generic", error=""))
        return False

    def _show_error(self, message: str) -> bool:
        self.phrase_label.set_label(self.state.t("error_generic", error=message))
        return False

    # -- audio -----------------------------------------------------------
    def _listen(self) -> None:
        if not self.phrase:
            return
        voice = default_voice_for_language(self.state.target)
        if not (voice_model_path(voice).exists() and voice_config_path(voice).exists()):
            self.banner.set_text(self.state.t("error_voice"))
            return

        def worker() -> None:
            path = TTS.synthesize_plain(self.phrase, voice, self.state.target, slow=True)
            if path:
                play_blocking(path)

        threading.Thread(target=worker, name="parley-say", daemon=True).start()

    def _ensure_recorder(self) -> Recorder | None:
        if self._recorder is None:
            self._recorder = Recorder()
        if not self._recorder.running:
            try:
                self._recorder.start()
            except Exception as exc:
                self.banner.set_text(self.state.t("error_mic", error=str(exc)))
                return None
        return self._recorder

    def _toggle_record(self) -> None:
        recorder = self._ensure_recorder()
        if recorder is None:
            return
        if not self._recording:
            self._player.stop()
            recorder.capture_start()
            self._recording = True
            self.record_button.set_label("■  " + self.state.t("finish"))
            self.record_button.add_css_class("mic")
        else:
            audio = recorder.capture_stop()
            self._recording = False
            self.record_button.set_label("🎙  " + self.state.t("your_turn"))
            self.record_button.remove_css_class("mic")
            if audio.size == 0:
                self.banner.set_text(self.state.t("error_mic", error="no audio"))
                return
            self._transcribe(audio)

    def _transcribe(self, audio) -> None:
        ensure_directories()
        self.banner.set_text(self.state.t("thinking"))
        path = AUDIO_DIR / "pronunciation.wav"
        write_wav(path, audio)

        def worker() -> None:
            try:
                result = STT.transcribe(path, self.state.whisper_model, self.state.target)
            except Exception as exc:
                GLib.idle_add(self._show_error, str(exc))
                return
            GLib.idle_add(self._show_result, result.text)

        threading.Thread(target=worker, name="parley-stt", daemon=True).start()

    def _show_result(self, heard: str) -> bool:
        self.banner.set_text("")
        results, accuracy = compare_reading(self.phrase, heard)
        self.score_label.set_label(f"{accuracy:.0f}%  {self.state.t('accuracy')}")
        self.result_label.set_markup(
            " ".join(
                word_markup(self.result_label, result.word, result.ok)
                for result in results
            )
        )
        self.heard_label.set_label(heard)
        return False

    def shutdown(self, *_args) -> None:
        if self._recorder is not None:
            self._recorder.stop()
            self._recorder = None
        self._player.stop()
