"""Voice practice session: live dialogue with the local model."""

from __future__ import annotations

import time

import gi

gi.require_version("Gtk", "4.0")

from gi.repository import GLib, Gtk

from ...audio import ConversationEngine
from ...core.scenarios import get_scenario
from ...core.scoring import TurnMetrics, save_session, score_turns
from ..helpers import (
    button,
    horizontal,
    label,
    note_markup,
    update_state_dot,
    vertical,
)

STATE_KEYS = {
    "listening": "listening",
    "thinking": "thinking",
    "speaking": "speaking",
    "paused": "paused",
    "recording": "your_turn",
    "idle": "paused",
    "error": "error_generic",
}


class SessionPage(Gtk.Box):
    def __init__(
        self,
        window,
        state,
        scenario_id: str = "meeting_someone_new",
        band: str = "beginner",
    ) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.window = window
        self.state = state
        self.scenario = get_scenario(scenario_id)
        self.band = band
        self.engine: ConversationEngine | None = None
        self._ai_label: Gtk.Label | None = None
        self._last_ai_text = ""
        self._backend_ready = False
        self._started_at = time.monotonic()
        self._turns: list[TurnMetrics] = []
        self._score_shown = False

        self._build_header()
        self._build_chat()
        self._build_controls()

        GLib.idle_add(self._boot)

    # -- layout ----------------------------------------------------------
    def _build_header(self) -> None:
        header = horizontal(12)
        header.set_margin_top(14)
        header.set_margin_start(22)
        header.set_margin_end(22)
        header.set_margin_bottom(6)

        titles = vertical(2)
        titles.set_hexpand(True)
        titles.append(label(self.scenario.label, "section-title", wrap=True))
        meta = horizontal(8)
        meta.append(label(self.state.t(self.band), f"pill pill-{self.band}"))
        meta.append(
            label(
                f"{self.state.t('target_language')}: {self._target_name()}",
                "muted",
            )
        )
        titles.append(meta)
        header.append(titles)

        self.status_dot = Gtk.Box()
        self.status_dot.add_css_class("state-dot")
        self.status_dot.set_valign(Gtk.Align.CENTER)
        header.append(self.status_dot)
        self.status_label = label(self.state.t("loading"), "muted")
        header.append(self.status_label)
        header.append(button(self.state.t("end_session"), "ghost", self._end))
        self.append(header)

        self.banner = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        self.banner.add_css_class("card")
        self.banner.set_margin_start(22)
        self.banner.set_margin_end(22)
        self.banner.set_margin_bottom(8)
        self.banner_text = label(self.state.t("ai_not_ready"), "muted", wrap=True)
        self.banner_text.set_hexpand(True)
        self.banner.append(self.banner_text)
        self.banner.append(button("↻", "ghost", self._retry_backend))
        self.append(self.banner)
        self.retry_button = self.banner.get_last_child()

    def _build_chat(self) -> None:
        self.chat_box = vertical(10)
        self.chat_box.set_margin_top(10)
        self.chat_box.set_margin_bottom(14)
        self.chat_box.set_margin_start(22)
        self.chat_box.set_margin_end(22)
        self.scroll = Gtk.ScrolledWindow()
        self.scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.scroll.set_vexpand(True)
        self.scroll.set_child(self.chat_box)
        self.scroll.add_css_class("chat-scroll")
        self.append(self.scroll)

    def _build_controls(self) -> None:
        bar = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        bar.set_margin_top(8)
        bar.set_margin_bottom(16)
        bar.set_margin_start(22)
        bar.set_margin_end(22)

        top = horizontal(12)
        self.mode_continuous = Gtk.ToggleButton(label=self.state.t("continuous_mode"))
        self.mode_ptt = Gtk.ToggleButton(label=self.state.t("push_to_talk"))
        self.mode_ptt.set_group(self.mode_continuous)
        if self.state.voice_mode == "push_to_talk":
            self.mode_ptt.set_active(True)
        else:
            self.mode_continuous.set_active(True)
        self.mode_continuous.connect("toggled", self._mode_changed)
        self.mode_ptt.connect("toggled", self._mode_changed)

        self.mic_button = Gtk.Button(label="🎙")
        self.mic_button.add_css_class("mic")
        self.mic_button.set_tooltip_text(self.state.t("push_to_talk"))

        click = Gtk.GestureClick()
        click.set_button(1)
        click.connect("pressed", self._mic_pressed)
        click.connect("released", self._mic_released)
        self.mic_button.add_controller(click)
        self.mic_button.connect("clicked", self._mic_clicked)

        self.level = Gtk.LevelBar()
        self.level.set_min_value(0.0)
        self.level.set_max_value(1.0)
        self.level.set_value(0.0)
        self.level.set_size_request(110, -1)
        self.level.set_valign(Gtk.Align.CENTER)

        top.append(self.mode_continuous)
        top.append(self.mode_ptt)
        top.append(self.mic_button)
        top.append(self.level)
        self.hint = label(self.state.t("listeners_note"), "muted", wrap=True)
        self.hint.set_hexpand(True)
        top.append(self.hint)
        top.append(button("🔁", "ghost", self._replay))
        bar.append(top)

        entry_row = horizontal(8)
        self.entry = Gtk.Entry()
        self.entry.set_placeholder_text(self.state.t("type_message"))
        self.entry.set_hexpand(True)
        self.entry.connect("activate", self._send_text)
        entry_row.append(self.entry)
        entry_row.append(button(self.state.t("send"), "primary", self._send_text))
        bar.append(entry_row)
        self.append(bar)

        self._update_mic_button()

    # -- lifecycle -------------------------------------------------------
    def _boot(self) -> bool:
        snapshot = self.state.snapshot()
        if snapshot.state == "running":
            self._backend_ready = True
            self.banner.set_visible(False)
            self._start_engine()
        else:
            self._backend_ready = False
            self.banner.set_visible(True)
            self._retry_backend()
        return False

    def _retry_backend(self) -> None:
        self.banner_text.set_label(self.state.t("ai_not_ready"))
        self.state.start_runtime()
        self.state.watch_runtime(self._on_snapshot)

    def _on_snapshot(self, snapshot) -> None:
        if snapshot.state == "running":
            self.banner.set_visible(False)
            if not self._backend_ready:
                self._backend_ready = True
                self._start_engine()
            return
        if snapshot.state == "error":
            self.banner.set_visible(True)
            self.banner_text.set_label(
                self.state.t("error_backend", error=snapshot.error or snapshot.message)
            )
            update_state_dot(self.status_dot, "error")
            self.status_label.set_label(self.state.t("paused"))
            return
        self.banner.set_visible(True)
        percent = max(0, min(100, snapshot.percent))
        message = snapshot.message or self.state.t("ai_not_ready")
        self.banner_text.set_label(f"{message}  ({percent}%)")

    def _start_engine(self) -> None:
        if self.engine is not None:
            return
        snapshot = self.state.snapshot()
        self.engine = ConversationEngine(
            self.scenario,
            self._on_event,
            backend=self.state.backend,
            base_url=snapshot.base_url or self.state.base_url,
            model=snapshot.model or self.state.model,
            target=self.state.target,
            native=self.state.native,
            level=self.scenario.level,
            whisper_model=self.state.whisper_model,
            tts_enabled=self.state.bool("tts_enabled", True),
            always_explain=self.state.bool("always_explain", True),
            correct_errors=self.state.bool("correct_errors", True),
        )
        self.state.engine = self.engine
        self.engine.start(self.state.voice_mode)

    def shutdown(self) -> None:
        self.state.stop_engine()
        self.engine = None

    def _end(self) -> None:
        self.shutdown()
        result = score_turns(self._turns) if self._turns else None
        if result is not None and result.turns:
            save_session(
                self.state.target,
                self.scenario.id,
                self.scenario.label,
                result,
            )
            self._show_score(result)
        self.window.reset_to("practice")

    def _show_score(self, result) -> None:
        dialog = Gtk.Window()
        dialog.set_modal(True)
        dialog.set_transient_for(self.window)
        dialog.set_title(self.state.t("session_score_title"))
        dialog.set_default_size(430, -1)
        dialog.set_resizable(False)

        box = vertical(12, 22)
        box.append(label(self.state.t("session_score_title"), "section-title", wrap=True))
        box.append(label(f"{result.score}/100", "score-big"))
        box.append(label(self.state.t(result.band_key), "card-title", wrap=True))
        box.append(
            label(
                self.state.t(
                    "session_score_body",
                    score=result.score,
                    level=self.state.t(result.band_key),
                    turns=result.turns,
                    words=result.words,
                ),
                "muted",
                wrap=True,
            )
        )
        box.append(label(self.state.t("progress_desc"), "progress-note", wrap=True))
        actions = horizontal(0)
        actions.set_halign(Gtk.Align.END)
        actions.append(button(self.state.t("close"), "primary", dialog.destroy))
        box.append(actions)
        dialog.set_child(box)
        dialog.present()

    # -- engine events ---------------------------------------------------
    def _on_event(self, event) -> None:
        GLib.idle_add(self._handle_event, event)

    def _handle_event(self, event) -> bool:
        kind = event.kind
        data = event.data
        if kind == "state":
            self._set_state(str(data.get("state") or "idle"))
        elif kind == "user_text":
            spoken = str(data.get("text") or "")
            words = int(data.get("words") or len(spoken.split()))
            self._turns.append(
                TurnMetrics(
                    text=spoken,
                    words=words,
                    speech_seconds=float(data.get("speech_seconds") or 0.0),
                    pause_ratio=float(data.get("pause_ratio") or 0.0),
                    words_per_minute=float(data.get("words_per_minute") or 0.0),
                    confidence=float(data.get("confidence") or 0.8),
                )
            )
            self._add_bubble(f"🧑  {spoken}", "bubble bubble-user", end=True)
        elif kind == "assistant_start":
            self._start_ai_bubble()
        elif kind == "assistant_delta":
            self._update_ai_bubble(str(data.get("text") or ""))
        elif kind == "assistant_done":
            self._update_ai_bubble(str(data.get("text") or ""))
            note = str(data.get("note") or "").strip()
            if note:
                note = note.lstrip("💡📝").strip()
                self._add_bubble(
                    note_markup(f"💡  {note}"),
                    "bubble bubble-note",
                    end=False,
                    markup=True,
                )
            self._ai_label = None
        elif kind == "error":
            detail = str(data.get("error") or "")
            key = {"mic": "error_mic", "backend": "error_backend"}.get(
                str(data.get("kind_detail") or ""), "error_generic"
            )
            self._add_bubble(self.state.t(key, error=detail), "bubble bubble-note", end=False)
        elif kind == "voice_missing":
            self._add_bubble(self.state.t("error_voice"), "bubble bubble-note", end=False)
        elif kind == "level":
            value = min(1.0, float(data.get("level") or 0.0) * 14.0)
            self.level.set_value(value)
        return False

    def _set_state(self, state: str) -> None:
        update_state_dot(self.status_dot, state if state in ("listening", "thinking", "speaking") else "paused")
        key = STATE_KEYS.get(state, "listening")
        if key == "error_generic":
            self.status_label.set_label(self.state.t("paused"))
        else:
            self.status_label.set_label(self.state.t(key))
        self.level.set_value(0.0 if state != "listening" else self.level.get_value())

    # -- chat ------------------------------------------------------------
    def _add_bubble(
        self, text: str, css: str, end: bool = False, markup: bool = False
    ) -> Gtk.Label:
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        bubble = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        for name in css.split():
            bubble.add_css_class(name)
        content = label(text, wrap=True, markup=markup)
        content.set_selectable(True)
        bubble.append(content)
        row.append(bubble)
        row.set_halign(Gtk.Align.END if end else Gtk.Align.START)
        self.chat_box.append(row)
        self._scroll_bottom()
        return content

    def _start_ai_bubble(self) -> None:
        self._last_ai_text = ""
        self._ai_label = self._add_bubble("…", "bubble bubble-ai")

    def _update_ai_bubble(self, text: str) -> None:
        if self._ai_label is None:
            self._ai_label = self._add_bubble(text, "bubble bubble-ai")
        elif text != self._last_ai_text:
            self._ai_label.set_label(text)
            self._last_ai_text = text
            self._scroll_bottom()

    def _scroll_bottom(self) -> None:
        def scroll():
            adjustment = self.scroll.get_vadjustment()
            adjustment.set_value(adjustment.get_upper() - adjustment.get_page_size())
            return False

        GLib.idle_add(scroll)

    # -- controls --------------------------------------------------------
    def _mode_changed(self, widget) -> None:
        if not widget.get_active() or self.engine is None:
            return
        mode = "push_to_talk" if self.mode_ptt.get_active() else "continuous"
        self.state.save(voice_mode=mode)
        self.engine.set_mode(mode)
        self._update_mic_button()

    def _update_mic_button(self) -> None:
        if self.state.voice_mode == "push_to_talk":
            self.mic_button.set_label("🎙")
            self.mic_button.remove_css_class("flat")
            self.mic_button.set_tooltip_text(self.state.t("push_to_talk"))
        else:
            self.mic_button.set_label("⏸")
            self.mic_button.add_css_class("flat")
            self.mic_button.set_tooltip_text(self.state.t("continuous_mode"))

    def _mic_pressed(self, gesture, n_press, x, y) -> None:
        self._pressed = True
        if self.engine is not None and self.state.voice_mode == "push_to_talk":
            self.engine.push_to_talk_start()
            self.mic_button.add_css_class("recording")
            self.mic_button.set_label("■")

    def _mic_released(self, gesture, n_press, x, y) -> None:
        if not getattr(self, "_pressed", False):
            return
        self._pressed = False
        if self.engine is not None and self.state.voice_mode == "push_to_talk":
            self.engine.push_to_talk_stop()
            self.mic_button.remove_css_class("recording")
            self.mic_button.set_label("🎙")

    def _mic_clicked(self, *_args) -> None:
        if self.engine is None:
            return
        if self.state.voice_mode == "push_to_talk":
            return
        paused = not self.engine.paused
        self.engine.set_paused(paused)
        self.mic_button.set_label("▶" if paused else "⏸")
        self.status_label.set_label(self.state.t("paused") if paused else self.state.t("listening"))

    def _send_text(self, *_args) -> None:
        text = self.entry.get_text().strip()
        if not text or self.engine is None:
            return
        self.entry.set_text("")
        self.engine.submit_text(text)

    def _replay(self) -> None:
        if self.engine is not None:
            self.engine.replay_last()

    def _target_name(self) -> str:
        from ...core.config import language_choice_label

        return language_choice_label(self.state.target)
