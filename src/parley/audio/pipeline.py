"""Conversation engine: microphone, speech-to-text, local LLM and speech.

The engine is pure Python. It emits ``EngineEvent`` objects from worker
threads; the GTK layer forwards them to the main loop with ``GLib.idle_add``.
"""

from __future__ import annotations

import queue
import re
import threading
import time
from dataclasses import dataclass, field

from ..core.config import (
    AUDIO_DIR,
    SETTINGS,
    default_voice_for_language,
    ensure_directories,
    voice_config_path,
    voice_model_path,
)
from ..core.llm import LLMError, stream_chat
from ..core.parser import parse_response
from ..core.prompts import build_system_prompt
from ..core.scenarios import Scenario
from ..core.stt import SpeechToText, STTError
from ..core.text import extract_questions
from ..core.tts import PiperTTS, TTSError
from .player import AudioPlayer
from .recorder import MicrophoneError, Recorder
from .wave_io import write_wav

TAG_RE = re.compile(r"<\s*/?\s*(?:MAIN|NOTE|EN|PT)\s*>", re.IGNORECASE)
NOTE_START_RE = re.compile(r"<\s*(?:NOTE|PT)\s*>", re.IGNORECASE)

OPENING_INSTRUCTION = (
    "Start the roleplay now. Write only your first in-character line in the "
    "main reply language, at most two short sentences, and end with a question "
    "for the learner. Do not include a note section in this first turn."
)


@dataclass
class EngineEvent:
    kind: str
    data: dict = field(default_factory=dict)


def _visible_main(raw: str) -> str:
    text = NOTE_START_RE.split(raw or "", maxsplit=1)[0]
    text = TAG_RE.sub("", text)
    return text.strip()


class ConversationEngine:
    def __init__(
        self,
        scenario: Scenario,
        on_event,
        backend: str,
        base_url: str,
        model: str,
        target: str,
        native: str,
        level: str | None = None,
        whisper_model: str = "base",
        tts_enabled: bool = True,
        always_explain: bool = True,
        correct_errors: bool = True,
    ) -> None:
        self.scenario = scenario
        self.on_event = on_event
        self.backend = backend
        self.base_url = base_url
        self.model = model
        self.target = target
        self.native = native
        self.level = level or scenario.level
        self.whisper_model = whisper_model
        self.tts_enabled = tts_enabled
        self.always_explain = always_explain
        self.correct_errors = correct_errors

        self._stt = SpeechToText()
        self._tts = PiperTTS()
        self._player = AudioPlayer()
        self._recorder = Recorder(
            on_utterance=self._on_utterance,
            on_level=self._on_level,
        )
        self._jobs: queue.Queue = queue.Queue()
        self._worker: threading.Thread | None = None
        self._running = threading.Event()
        self._paused = threading.Event()
        self._mode = "continuous"
        self._state = "idle"
        self._messages: list[dict] = []
        self._asked_questions: list[str] = []
        self._speaking = threading.Event()
        self._last_level = 0.0
        self._last_level_at = 0.0

    # -- lifecycle -------------------------------------------------------
    @property
    def state(self) -> str:
        return self._state

    @property
    def mode(self) -> str:
        return self._mode

    @property
    def paused(self) -> bool:
        return self._paused.is_set()

    def start(self, mode: str = "continuous") -> None:
        self._mode = "push_to_talk" if mode == "push_to_talk" else "continuous"
        self._running.set()
        self._worker = threading.Thread(target=self._work_loop, name="parley-engine", daemon=True)
        self._worker.start()
        try:
            self._recorder.start()
        except MicrophoneError as exc:
            self._emit("error", error=str(exc), kind_detail="mic")
        ensure_directories()
        self._enqueue(self._opening)

    def stop(self) -> None:
        self._running.clear()
        self._player.stop()
        self._recorder.stop()
        self._jobs.put(None)
        if self._worker and self._worker.is_alive():
            self._worker.join(timeout=1.0)
        self._worker = None
        self._set_state("idle")

    def set_mode(self, mode: str) -> None:
        self._mode = "push_to_talk" if mode == "push_to_talk" else "continuous"
        self._player.stop()
        self._recorder.set_suppressed(False)
        if self._mode == "continuous":
            self._set_state("paused" if self._paused.is_set() else "listening")

    def set_paused(self, paused: bool) -> None:
        if paused:
            self._paused.set()
        else:
            self._paused.clear()
        if self._mode == "continuous":
            self._set_state("paused" if paused else "listening")

    def push_to_talk_start(self) -> None:
        if self._mode != "push_to_talk":
            return
        self._player.stop()
        self._recorder.capture_start()
        self._set_state("recording")

    def push_to_talk_stop(self) -> None:
        if self._mode != "push_to_talk":
            return
        audio = self._recorder.capture_stop()
        if audio.size == 0:
            self._set_state("listening")
            return
        self._enqueue(lambda: self._handle_audio(audio, source="voice"))
        self._set_state("thinking")

    def submit_text(self, text: str) -> None:
        cleaned = (text or "").strip()
        if not cleaned:
            return
        self._emit("user_text", text=cleaned)
        self._enqueue(lambda: self._respond(cleaned))

    def replay_last(self) -> None:
        self._enqueue(self._replay_last)

    # -- worker ----------------------------------------------------------
    def _enqueue(self, job) -> None:
        self._jobs.put(job)

    def _work_loop(self) -> None:
        while self._running.is_set():
            try:
                job = self._jobs.get(timeout=0.25)
            except queue.Empty:
                continue
            if job is None:
                break
            try:
                job()
            except Exception as exc:  # pragma: no cover - defensive
                self._emit("error", error=str(exc), kind_detail="generic")
                self._set_state("listening")
        self._enable_input()

    def _opening(self) -> None:
        self._messages = [
            {
                "role": "system",
                "content": build_system_prompt(
                    self.scenario,
                    self.level,
                    always_explain=self.always_explain,
                    correct_errors=self.correct_errors,
                    reply_language=self.target,
                    target_language=self.target,
                    native_language=self.native,
                ),
            },
            {"role": "user", "content": OPENING_INSTRUCTION},
        ]
        self._stream_reply(display_user=False)

    def _respond(self, text: str) -> None:
        self._messages.append({"role": "user", "content": text})
        self._trim_history()
        self._refresh_system_prompt()
        self._stream_reply(display_user=False)

    def _refresh_system_prompt(self) -> None:
        """Rebuild the system prompt with the questions already asked."""

        if not self._messages:
            return
        system = self._messages[0]
        if system.get("role") != "system":
            return
        system["content"] = build_system_prompt(
            self.scenario,
            self.level,
            always_explain=self.always_explain,
            correct_errors=self.correct_errors,
            reply_language=self.target,
            target_language=self.target,
            native_language=self.native,
            asked_questions=self._asked_questions,
        )

    def _trim_history(self) -> None:
        limit = max(2, SETTINGS.history_turns * 2)
        system = [message for message in self._messages if message.get("role") == "system"]
        rest = [message for message in self._messages if message.get("role") != "system"]
        self._messages = system + rest[-limit:]

    def _stream_reply(self, display_user: bool = False) -> None:
        self._set_state("thinking")
        self._emit("assistant_start")
        raw = ""
        visible = ""
        try:
            for chunk in stream_chat(
                SETTINGS, self.backend, self.base_url, self.model, self._messages
            ):
                raw += chunk
                new_visible = _visible_main(raw)
                if new_visible != visible:
                    visible = new_visible
                    self._emit("assistant_delta", text=visible)
        except LLMError as exc:
            self._emit("error", error=str(exc), kind_detail="backend")
            self._set_state("listening")
            self._enable_input()
            return
        except Exception as exc:  # pragma: no cover - defensive
            self._emit("error", error=str(exc), kind_detail="generic")
            self._set_state("listening")
            self._enable_input()
            return

        parsed = parse_response(
            raw,
            always_explain=self.always_explain,
            main_lang=self.target,
            note_lang=self.native,
        )
        main_text = parsed.english or visible or raw.strip()
        note_text = parsed.portuguese or ""
        self._messages.append({"role": "assistant", "content": main_text})
        self._asked_questions.extend(extract_questions(main_text))
        self._asked_questions = self._asked_questions[-12:]
        self._emit("assistant_done", text=main_text, note=note_text, raw=raw)
        self._speak(main_text)
        self._set_state("listening")
        self._enable_input()

    def _speak(self, text: str) -> None:
        if not self.tts_enabled or not text.strip():
            return
        voice = default_voice_for_language(self.target)
        if not (voice_model_path(voice).exists() and voice_config_path(voice).exists()):
            self._emit("voice_missing", voice=voice)
            return
        try:
            path = self._tts.synthesize_plain(text, voice, self.target)
        except TTSError as exc:
            self._emit("error", error=str(exc), kind_detail="tts")
            return
        if not path:
            return
        self._set_state("speaking")
        self._speaking.set()
        self._recorder.set_suppressed(True)
        try:
            self._player.play(path)
            deadline = time.monotonic() + max(15.0, len(text) / 8.0)
            while self._player.playing and time.monotonic() < deadline:
                if not self._running.is_set():
                    break
                time.sleep(0.05)
            self._player.stop(keep_position=True)
        finally:
            self._speaking.clear()
            if self._running.is_set():
                time.sleep(0.25)
                self._recorder.set_suppressed(False)
                self._set_state("listening")

    def _replay_last(self) -> None:
        last = ""
        for message in reversed(self._messages):
            if message.get("role") == "assistant":
                last = str(message.get("content") or "")
                break
        if last:
            self._speak(last)

    # -- capture ---------------------------------------------------------
    def _on_utterance(self, audio) -> None:
        if self._mode != "continuous" or self._paused.is_set():
            return
        if self._speaking.is_set():
            return
        self._set_state("thinking")
        self._enqueue(lambda: self._handle_audio(audio, source="voice"))

    def _on_level(self, level: float) -> None:
        now = time.monotonic()
        if now - self._last_level_at < 0.08:
            return
        self._last_level_at = now
        if abs(level - self._last_level) < 0.004:
            return
        self._last_level = level
        self._emit("level", level=level)

    def _handle_audio(self, audio, source: str = "voice") -> None:
        ensure_directories()
        path = AUDIO_DIR / f"input-{int(time.time() * 1000)}.wav"
        try:
            write_wav(path, audio)
            result = self._stt.transcribe(path, self.whisper_model, self.target)
        except (STTError, OSError) as exc:
            self._emit("error", error=str(exc), kind_detail="stt")
            self._set_state("listening")
            self._enable_input()
            return
        finally:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass
        text = (result.text or "").strip()
        if not text:
            self._set_state("listening")
            self._enable_input()
            return
        self._emit(
            "user_text",
            text=text,
            words=result.words,
            speech_seconds=result.speech_duration,
            pause_ratio=result.pause_ratio,
            words_per_minute=result.words_per_minute,
            confidence=result.confidence,
        )
        self._respond(text)

    # -- helpers ---------------------------------------------------------
    def _enable_input(self) -> None:
        if self._mode == "continuous" and self._running.is_set():
            self._set_state("paused" if self._paused.is_set() else "listening")

    def _set_state(self, state: str) -> None:
        if state == self._state:
            return
        self._state = state
        self._emit("state", state=state)

    def _emit(self, kind: str, **data) -> None:
        if not self.on_event:
            return
        try:
            self.on_event(EngineEvent(kind=kind, data=data))
        except Exception:
            pass
