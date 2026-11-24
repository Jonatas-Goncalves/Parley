"""Settings: languages, AI backend, model, voices and content."""

from __future__ import annotations

import threading
import time

import gi

gi.require_version("Gtk", "4.0")

from gi.repository import GLib, Gtk

from ... import __version__
from ...content import stories
from ...core.backends import RUNTIME
from ...core.config import (
    PIPER_VOICE_REGISTRY,
    SUPPORTED_LANGUAGES,
    WHISPER_MODELS,
    language_choice_label,
    voices_for_language,
)
from ...core.health import environment_report
from ...core.i18n import UI_LANGUAGES
from ...core.model_manager import for_tier, installed_tiers, remove_gguf, remove_ollama_model
from ...core.voice_manager import VoiceManager
from ..fonts import cjk_font_available, needs_cjk_font
from ..helpers import (
    button,
    card,
    confirm_dialog,
    horizontal,
    label,
    page_body,
    page_scroll,
    vertical,
)

VOICE_MANAGER = VoiceManager()


def _dropdown(options: list[tuple[str, str]], current: str) -> tuple[Gtk.DropDown, Gtk.StringList]:
    store = Gtk.StringList()
    for text, _value in options:
        store.append(text)
    widget = Gtk.DropDown(model=store)
    for index, (_text, value) in enumerate(options):
        if value == current:
            widget.set_selected(index)
            break
    widget.set_hexpand(True)
    return widget, store


def _value_at(options: list[tuple[str, str]], index: int) -> str:
    if 0 <= index < len(options):
        return options[index][1]
    return options[0][1] if options else ""


class SettingsPage(Gtk.Box):
    def __init__(self, window, state) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.window = window
        self.state = state
        self._story_index = stories.load_index()
        self._last_confirm: Gtk.Window | None = None
        self._model_source = 0
        self._installed_tiers: dict[str, bool] = {}
        self._suppress_tier = False

        body = page_body()
        body.append(label(state.t("settings"), "hero-title", wrap=True))
        body.append(self._language_card())
        body.append(self._ai_card())
        body.append(self._speech_card())
        body.append(self._stories_card())
        body.append(self._diagnostics_card())
        self.append(page_scroll(body))
        self._refresh_stories_index()

    # -- language --------------------------------------------------------
    def _language_card(self) -> Gtk.Box:
        outer, inner = card()

        ui_options = [(label_text, code) for code, label_text in UI_LANGUAGES.items()]
        self.ui_dropdown, _ = _dropdown(ui_options, self.state.ui_language)
        self.ui_dropdown.connect("notify::selected", self._ui_language_changed)
        inner.append(self._row(self.state.t("interface_language"), self.ui_dropdown))

        theme_options = [
            (self.state.t("theme_system"), "system"),
            (self.state.t("theme_light"), "light"),
            (self.state.t("theme_dark"), "dark"),
        ]
        self.theme_dropdown, _ = _dropdown(theme_options, self.state.theme_mode)
        self.theme_dropdown.connect("notify::selected", self._theme_changed)
        inner.append(self._row(self.state.t("theme"), self.theme_dropdown))

        lang_options = [(language_choice_label(code), code) for code in SUPPORTED_LANGUAGES]
        self.native_dropdown, _ = _dropdown(lang_options, self.state.native)
        self.native_dropdown.connect("notify::selected", self._native_changed)
        inner.append(self._row(self.state.t("native_language"), self.native_dropdown))

        self.target_dropdown, _ = _dropdown(lang_options, self.state.target)
        self.target_dropdown.connect("notify::selected", self._target_changed)
        inner.append(self._row(self.state.t("target_language"), self.target_dropdown))

        self.font_hint = label(self.state.t("cjk_font_hint"), "error-text", wrap=True)
        inner.append(self.font_hint)
        self._update_font_hint()
        return outer

    def _update_font_hint(self) -> None:
        show = needs_cjk_font(self.state.target) and not cjk_font_available()
        self.font_hint.set_visible(show)

    def _row(self, title: str, widget: Gtk.Widget) -> Gtk.Box:
        row = horizontal(16)
        text = label(title, wrap=True)
        text.set_size_request(190, -1)
        row.append(text)
        widget.set_hexpand(True)
        row.append(widget)
        return row

    def _ui_language_changed(self, *_args) -> None:
        options = [(label_text, code) for code, label_text in UI_LANGUAGES.items()]
        code = _value_at(options, self.ui_dropdown.get_selected())
        if code == self.state.ui_language:
            return
        self.state.save(ui_language=code)
        self.window.refresh()

    def _theme_changed(self, *_args) -> None:
        options = [
            (self.state.t("theme_system"), "system"),
            (self.state.t("theme_light"), "light"),
            (self.state.t("theme_dark"), "dark"),
        ]
        theme = _value_at(options, self.theme_dropdown.get_selected())
        if theme == self.state.theme_mode:
            return
        self.state.save(theme=theme)
        self.window.apply_theme()

    def _native_changed(self, *_args) -> None:
        options = [(language_choice_label(code), code) for code in SUPPORTED_LANGUAGES]
        code = _value_at(options, self.native_dropdown.get_selected())
        if code == self.state.native:
            return
        self.state.save(native=code)

    def _target_changed(self, *_args) -> None:
        options = [(language_choice_label(code), code) for code in SUPPORTED_LANGUAGES]
        code = _value_at(options, self.target_dropdown.get_selected())
        if code == self.state.target:
            return
        self.state.save(target=code)
        self._refresh_voices()
        self._update_font_hint()

    # -- AI --------------------------------------------------------------
    def _ai_card(self) -> Gtk.Box:
        outer, inner = card()
        inner.append(label(self.state.t("ai_backend"), "card-title"))

        self.backend_toggle = horizontal(8)
        self.ollama_button = Gtk.ToggleButton(label="Ollama")
        self.llamacpp_button = Gtk.ToggleButton(label="llama.cpp")
        self.llamacpp_button.set_group(self.ollama_button)
        (self.llamacpp_button if self.state.backend == "llamacpp" else self.ollama_button).set_active(True)
        self.ollama_button.connect("toggled", self._backend_changed)
        self.llamacpp_button.connect("toggled", self._backend_changed)
        self.backend_toggle.append(self.ollama_button)
        self.backend_toggle.append(self.llamacpp_button)
        inner.append(self.backend_toggle)

        self.backend_status_label = Gtk.Label()
        self.backend_status_label.set_xalign(0)
        self.backend_status_label.set_use_markup(True)
        self.backend_status_label.set_wrap(True)
        self._set_backend_status(False)
        inner.append(self.backend_status_label)

        inner.append(label(self.state.t("ai_model"), "card-title"))
        tiers = horizontal(8)
        self.tier_buttons: dict[str, Gtk.ToggleButton] = {}
        first = None
        for tier in ("weak", "medium", "strong"):
            widget = Gtk.ToggleButton(label=self._tier_label(tier, None))
            widget.set_hexpand(True)
            if first is None:
                widget.set_group(None)
                first = widget
            else:
                widget.set_group(first)
            if tier == self.state.model_tier:
                widget.set_active(True)
            widget.connect("toggled", lambda widget, tier=tier: self._tier_changed(widget, tier))
            widget.connect("clicked", lambda widget, tier=tier: self._tier_clicked(widget, tier))
            self.tier_buttons[tier] = widget
            tiers.append(widget)
        inner.append(tiers)

        self.tier_detail = label(self._tier_text(), "muted", wrap=True)
        inner.append(self.tier_detail)
        inner.append(label(self.state.t("model_quality_warning"), "muted", wrap=True))

        self.model_progress = Gtk.ProgressBar()
        self.model_progress.set_visible(False)
        inner.append(self.model_progress)
        self.model_status = label("", "muted", wrap=True)
        self.model_status.set_visible(False)
        inner.append(self.model_status)

        self.cancel_download_button = button(
            self.state.t("cancel"), "ghost", self._cancel_model_download
        )
        self.cancel_download_button.set_visible(False)
        inner.append(self.cancel_download_button)

        inner.append(label(self.state.t("remove_model"), "card-title"))
        remove_row = horizontal(8)
        self.remove_tier_buttons: dict[str, Gtk.Button] = {}
        for tier in ("weak", "medium", "strong"):
            btn = button(
                self.state.t(f"model_{tier}"),
                "ghost",
                lambda t=tier: self._remove_tier_model(t),
            )
            btn.set_hexpand(True)
            btn.set_sensitive(False)
            self.remove_tier_buttons[tier] = btn
            remove_row.append(btn)
        inner.append(remove_row)

        inner.append(label(self.state.t("custom_model"), "card-title"))
        self.custom_model_status = label("", "muted", wrap=True)
        inner.append(self.custom_model_status)
        custom_row = horizontal(8)
        custom_row.append(
            button(self.state.t("select_gguf_file"), "ghost", self._pick_custom_gguf)
        )
        custom_row.append(
            button(self.state.t("clear_custom_model"), "ghost", self._clear_custom_gguf)
        )
        inner.append(custom_row)

        self._refresh_installed()
        self._refresh_custom_model_status()
        return outer

    def _tier_label(self, tier: str, installed: bool | None) -> str:
        base = self.state.t(f"model_{tier}")
        if installed is None:
            return base
        marker = "✓" if installed else "⬇"
        return f"{base}  {marker}"

    def _update_tier_labels(self) -> None:
        for tier, widget in self.tier_buttons.items():
            installed = self._installed_tiers.get(tier)
            widget.set_label(self._tier_label(tier, installed))
            remove_btn = self.remove_tier_buttons.get(tier)
            if remove_btn is not None:
                remove_btn.set_sensitive(installed is True)
            if installed is None:
                continue
            widget.set_tooltip_text(
                self.state.t("model_installed")
                if installed
                else self.state.t("model_not_downloaded")
            )

    def _refresh_installed(self) -> None:
        backend = self.state.backend
        base_url = self.state.base_url

        def worker() -> None:
            try:
                result = installed_tiers(backend, base_url)
            except Exception:
                result = {}
            GLib.idle_add(self._apply_installed, result)

        threading.Thread(
            target=worker, name="parley-model-check", daemon=True
        ).start()

    def _apply_installed(self, result: dict[str, bool]) -> bool:
        if isinstance(result, dict):
            self._installed_tiers = dict(result)
            self._update_tier_labels()
        return False

    def _tier_text(self) -> str:
        spec = for_tier(self.state.model_tier)
        return f"{spec.label} · {spec.size_gb:.1f} GB · RAM ≥ {spec.min_ram_gb:.0f} GB — {spec.description}"

    def _tier_changed(self, widget, tier: str) -> None:
        if self._suppress_tier or not widget.get_active():
            return
        if tier == self.state.model_tier:
            return
        installed = self._installed_tiers.get(tier)
        if installed is None:
            self._check_tier(tier)
            return
        if installed is False:
            self._confirm_tier(tier)
            return
        self._apply_tier(tier)

    def _check_tier(self, tier: str) -> None:
        backend = self.state.backend
        base_url = self.state.base_url

        def worker() -> None:
            try:
                result = installed_tiers(backend, base_url)
            except Exception:
                result = {}
            GLib.idle_add(self._tier_checked, tier, result)

        threading.Thread(
            target=worker, name="parley-model-check-tier", daemon=True
        ).start()

    def _tier_checked(self, tier: str, result: dict[str, bool]) -> bool:
        self._apply_installed(result)
        button = self.tier_buttons.get(tier)
        if button is None or not button.get_active():
            return False
        if self._installed_tiers.get(tier) is True:
            self._apply_tier(tier)
        else:
            self._confirm_tier(tier)
        return False

    def _confirm_tier(self, tier: str) -> None:
        spec = for_tier(tier)
        self._last_confirm = confirm_dialog(
            self.window,
            self.state.t("model_download_title"),
            self.state.t(
                "model_download_confirm",
                tier=self.state.t(f"model_{tier}"),
                model=spec.label,
                size=f"{spec.size_gb:.1f}",
            ),
            self.state.t("download"),
            lambda: self._apply_tier(tier),
            cancel=self.state.t("cancel"),
            on_cancel=self._revert_tier,
        )

    def _apply_tier(self, tier: str) -> None:
        self.state.save(model_tier=tier, model="")
        self.tier_detail.set_label(self._tier_text())
        self._restart_backend()

    def _revert_tier(self) -> None:
        previous = self.state.model_tier
        button = self.tier_buttons.get(previous)
        if button is None:
            return
        self._suppress_tier = True
        button.set_active(True)
        self._suppress_tier = False

    def _tier_clicked(self, widget: Gtk.ToggleButton, tier: str) -> None:
        if self._suppress_tier:
            return
        if not widget.get_active():
            return
        # Re-trigger download/check if the selected tier's file is missing.
        if tier == self.state.model_tier:
            installed = self._installed_tiers.get(tier)
            if installed is False:
                self._confirm_tier(tier)
            elif installed is None:
                self._check_tier(tier)

    def _cancel_model_download(self) -> None:
        try:
            RUNTIME.stop()
        except Exception:
            pass
        self.model_status.set_visible(True)
        self.model_status.set_label(self.state.t("cancelled"))
        self.model_progress.set_visible(False)
        self.cancel_download_button.set_visible(False)
        self._set_backend_status(False)

    def _remove_tier_model(self, tier: str) -> None:
        spec = for_tier(tier)
        self._last_confirm = confirm_dialog(
            self.window,
            self.state.t("remove_model"),
            self.state.t("remove_model_confirm", model=spec.label),
            self.state.t("remove_model"),
            lambda: self._do_remove_tier_model(tier),
            cancel=self.state.t("cancel"),
        )

    def _do_remove_tier_model(self, tier: str) -> None:
        spec = for_tier(tier)
        backend = self.state.backend

        def worker() -> None:
            error = ""
            removed = False
            try:
                if backend == "ollama":
                    removed = remove_ollama_model(spec.ollama_tag, self.state.base_url)
                else:
                    removed = remove_gguf(spec)
                logger_msg = f"remove tier={tier} backend={backend} removed={removed}"
                print(f"[Parley] {logger_msg}", flush=True)
            except Exception as exc:
                error = str(exc) or exc.__class__.__name__
                print(f"[Parley] remove tier={tier} failed: {error}", flush=True)
            GLib.idle_add(self._after_remove_tier_model, tier, error, removed)

        threading.Thread(
            target=worker, name="parley-model-remove", daemon=True
        ).start()

    def _after_remove_tier_model(self, tier: str, error: str, removed: bool = False) -> bool:
        if error:
            self.model_status.set_visible(True)
            self.model_status.set_label(
                self.state.t("error_backend", error=error)
            )
        else:
            self.model_status.set_visible(True)
            if removed:
                self.model_status.set_label(self.state.t("model_removed"))
            else:
                self.model_status.set_label(self.state.t("model_removed") + " (file not found)")
            if tier == self.state.model_tier and not self.state.custom_gguf_path:
                try:
                    RUNTIME.stop()
                except Exception:
                    pass
                self.cancel_download_button.set_visible(False)
                self._set_backend_status(False)
        self._refresh_installed()
        return False

    def _refresh_custom_model_status(self) -> None:
        path = self.state.custom_gguf_path
        if path:
            from pathlib import Path as _Path

            p = _Path(path).expanduser()
            if p.is_file():
                self.custom_model_status.set_label(
                    self.state.t("custom_model_active", path=p.name)
                )
            else:
                self.custom_model_status.set_label(
                    self.state.t("custom_model_active", path=path)
                )
        else:
            self.custom_model_status.set_label(self.state.t("custom_model_none"))

    def _pick_custom_gguf(self) -> None:
        dialog = Gtk.FileChooserNative.new(
            self.state.t("select_gguf_file"),
            self.window,
            Gtk.FileChooserAction.OPEN,
            self.state.t("select_gguf_file"),
            self.state.t("cancel"),
        )
        gguf_filter = Gtk.FileFilter()
        gguf_filter.set_name("GGUF")
        gguf_filter.add_pattern("*.gguf")
        dialog.add_filter(gguf_filter)
        any_filter = Gtk.FileFilter()
        any_filter.set_name("All files")
        any_filter.add_pattern("*")
        dialog.add_filter(any_filter)

        def on_response(dlg, response):
            try:
                if response == Gtk.ResponseType.ACCEPT:
                    file = dlg.get_file()
                    if file is not None:
                        path = file.get_path()
                        if path:
                            self.state.save(
                                custom_gguf_path=path,
                                backend="llamacpp",
                                backend_explicit=True,
                            )
                            self._refresh_custom_model_status()
                            self._restart_backend()
            finally:
                dlg.destroy()

        dialog.connect("response", on_response)
        dialog.show()

    def _clear_custom_gguf(self) -> None:
        self.state.save(custom_gguf_path="")
        self._refresh_custom_model_status()
        self._restart_backend()

    def _backend_changed(self, widget) -> None:
        if not widget.get_active():
            return
        backend = "llamacpp" if self.llamacpp_button.get_active() else "ollama"
        if backend == self.state.backend:
            return
        self.state.save(backend=backend, backend_explicit=True, base_url="", model="")
        self._restart_backend()

    def _restart_backend(self) -> None:
        try:
            RUNTIME.stop()
        except Exception:
            pass
        self._watch_model()

        def worker() -> None:
            # Let a cancelled pull unwind before starting the new backend.
            for _attempt in range(400):
                if not RUNTIME.busy():
                    break
                time.sleep(0.1)
            self.state.start_runtime()

        threading.Thread(
            target=worker, name="parley-backend-restart", daemon=True
        ).start()

    def _set_backend_status(self, ready: bool) -> None:
        status = "READY" if ready else "NOT READY"
        color = "#4CAF50" if ready else "#F44336"
        self.backend_status_label.set_markup(
            f'<b>STATUS:</b> <span foreground="{color}"><b>{status}</b></span>'
        )

    def _watch_model(self) -> None:
        if self._model_source:
            GLib.source_remove(self._model_source)
            self._model_source = 0
        self.model_status.set_visible(True)
        self.model_status.set_label(self.state.t("ai_not_ready"))
        self.model_progress.set_visible(True)
        self.model_progress.set_fraction(0.0)
        self.cancel_download_button.set_visible(True)
        self._set_backend_status(False)

        def tick() -> bool:
            snapshot = RUNTIME.snapshot()
            percent = max(0, min(100, int(snapshot.percent or 0)))
            self.model_progress.set_fraction(percent / 100.0)
            self._set_backend_status(snapshot.state == "running")
            if snapshot.state == "running":
                self.model_progress.set_visible(False)
                self.cancel_download_button.set_visible(False)
                self.model_status.set_label(
                    self.state.t("model_ready", model=snapshot.model)
                )
                self._model_source = 0
                self._refresh_installed()
                return False
            if snapshot.state == "error":
                self.model_progress.set_visible(False)
                self.cancel_download_button.set_visible(False)
                self.model_status.set_label(
                    self.state.t(
                        "error_backend", error=snapshot.error or snapshot.message
                    )
                )
                self._model_source = 0
                return False
            message = snapshot.message or self.state.t("ai_not_ready")
            self.model_status.set_label(f"{message} · {percent}%")
            return True

        self._model_source = GLib.timeout_add(400, tick)

    def shutdown(self) -> None:
        if self._model_source:
            GLib.source_remove(self._model_source)
            self._model_source = 0

    # -- speech ----------------------------------------------------------
    def _speech_card(self) -> Gtk.Box:
        outer, inner = card()

        whisper_options = [(name, name) for name in WHISPER_MODELS]
        self.whisper_dropdown, _ = _dropdown(whisper_options, self.state.whisper_model)
        self.whisper_dropdown.connect("notify::selected", self._whisper_changed)
        inner.append(self._row(self.state.t("whisper_model"), self.whisper_dropdown))

        tts_options = [
            (self.state.t("on"), "on"),
            (self.state.t("off"), "off"),
        ]
        current_tts = "on" if self.state.bool("tts_enabled", True) else "off"
        self.tts_dropdown, _ = _dropdown(tts_options, current_tts)
        self.tts_dropdown.connect("notify::selected", self._tts_changed)
        inner.append(self._row(self.state.t("speak_replies"), self.tts_dropdown))

        voice_options = self._voice_options()
        self.voice_dropdown, _ = _dropdown(voice_options, self._current_voice())
        inner.append(self._row(self.state.t("voice"), self.voice_dropdown))

        actions = horizontal(8)
        actions.append(button(self.state.t("download_voice"), "ghost", self._download_voice))
        self.voice_status = label("", "muted", wrap=True)
        actions.append(self.voice_status)
        inner.append(actions)

        inner.append(label(self.state.t("voice_installed_voices"), "card-title"))
        self.voices_box = vertical(6)
        inner.append(self.voices_box)
        self._refresh_downloaded_voices()
        self._refresh_voice_status()
        return outer

    def _voice_options(self) -> list[tuple[str, str]]:
        voices = voices_for_language(self.state.target, downloaded_only=False)
        if not voices:
            return [("—", "")]
        options = []
        for voice, name in voices.items():
            options.append((name, voice))
        return options

    def _current_voice(self) -> str:
        from ...core.config import default_voice_for_language

        return default_voice_for_language(self.state.target)

    def _refresh_voices(self) -> None:
        options = self._voice_options()
        store = Gtk.StringList()
        for text, _value in options:
            store.append(text)
        self.voice_dropdown.set_model(store)
        self._refresh_voice_status()

    def _refresh_voice_status(self) -> None:
        from ...core.config import voice_config_path, voice_model_path

        voice = self._current_voice()
        ready = voice_model_path(voice).exists() and voice_config_path(voice).exists()
        self.voice_status.set_label("✓" if ready else "—")
        self.voice_status.remove_css_class("error-text")
        if not ready:
            self.voice_status.set_label(self.state.t("error_voice"))

    def _refresh_downloaded_voices(self) -> None:
        while True:
            child = self.voices_box.get_first_child()
            if child is None:
                break
            self.voices_box.remove(child)
        downloaded = VOICE_MANAGER.list_downloaded()
        if not downloaded:
            self.voices_box.append(
                label(self.state.t("voice_none_installed"), "muted", wrap=True)
            )
            return
        for voice in downloaded:
            row = horizontal(8)
            name = PIPER_VOICE_REGISTRY.get(voice, {}).get("name", voice)
            text = label(f"{name}  ·  {voice}", wrap=True)
            text.set_hexpand(True)
            row.append(text)
            delete = button(
                "🗑",
                "ghost",
                lambda voice=voice, name=name: self._ask_delete_voice(voice, name),
            )
            delete.set_tooltip_text(self.state.t("voice_delete"))
            row.append(delete)
            self.voices_box.append(row)

    def _ask_delete_voice(self, voice: str, name: str) -> None:
        self._last_confirm = confirm_dialog(
            self.window,
            self.state.t("voice_delete"),
            self.state.t("voice_delete_confirm", voice=name),
            self.state.t("voice_delete"),
            lambda: self._delete_voice(voice),
            cancel=self.state.t("cancel"),
        )

    def _delete_voice(self, voice: str) -> None:
        ok, message = VOICE_MANAGER.delete_voice(voice)
        self._refresh_downloaded_voices()
        self._refresh_voices()
        self.voice_status.set_label(
            self.state.t("voice_deleted") if ok else message
        )
        if ok:
            self.voice_status.remove_css_class("error-text")
        else:
            self.voice_status.add_css_class("error-text")

    def _download_voice(self) -> None:
        from ...core.config import default_voice_for_language

        voice = default_voice_for_language(self.state.target)
        self.voice_status.set_label(self.state.t("loading"))

        def worker() -> None:
            ok, message = VOICE_MANAGER.download_voice(voice)

            def update() -> bool:
                self.voice_status.set_label(message)
                self._refresh_downloaded_voices()
                self._refresh_voice_status()
                return False

            GLib.idle_add(update)

        threading.Thread(target=worker, name="parley-voice", daemon=True).start()

    def _whisper_changed(self, *_args) -> None:
        options = [(name, name) for name in WHISPER_MODELS]
        self.state.save(whisper_model=_value_at(options, self.whisper_dropdown.get_selected()))

    def _tts_changed(self, *_args) -> None:
        options = [
            (self.state.t("on"), "on"),
            (self.state.t("off"), "off"),
        ]
        value = _value_at(options, self.tts_dropdown.get_selected())
        self.state.save(tts_enabled=value == "on")

    # -- stories ---------------------------------------------------------
    def _stories_card(self) -> Gtk.Box:
        outer, inner = card(self.state.t("stories_section"))
        index = self._story_index
        size = index.total_megabytes
        self.stories_status = label(
            self.state.t("stories_available", count=index.count, size=f"{size:.1f}"),
            "card-subtitle",
            wrap=True,
        )
        inner.append(self.stories_status)
        self.stories_progress = Gtk.ProgressBar()
        self.stories_progress.set_visible(False)
        inner.append(self.stories_progress)

        actions = horizontal(8)
        self.download_button = button(
            self.state.t("stories_download"), "primary", self._ask_download_stories
        )
        actions.append(self.download_button)
        actions.append(button(self.state.t("stories_remove"), "ghost", self._remove_stories))
        inner.append(actions)
        return outer

    def _refresh_stories_index(self) -> None:
        def worker() -> None:
            try:
                index = stories.remote_index()
            except Exception:
                index = stories.load_index()
            GLib.idle_add(self._apply_stories_index, index)

        threading.Thread(target=worker, name="parley-stories-index", daemon=True).start()

    def _apply_stories_index(self, index) -> bool:
        self._story_index = index
        size = index.total_megabytes
        self.stories_status.set_label(
            self.state.t("stories_available", count=index.count, size=f"{size:.1f}")
        )
        self.stories_status.remove_css_class("error-text")
        return False

    def _ask_download_stories(self) -> None:
        index = self._story_index
        text = self.state.t(
            "stories_download_confirm",
            count=index.count,
            size=f"{index.total_megabytes:.1f}",
        )
        self._last_confirm = confirm_dialog(
            self.window,
            self.state.t("stories_download"),
            text,
            self.state.t("stories_download"),
            self._download_stories,
        )

    def _download_stories(self) -> None:
        self.stories_progress.set_visible(True)
        self.stories_progress.set_fraction(0.0)
        self.download_button.set_sensitive(False)

        def progress(position, count, done, total, title) -> None:
            fraction = min(1.0, done / float(total or 1))
            GLib.idle_add(self._update_progress, fraction, position, count, title)

        def worker() -> None:
            errors = stories.download(self._story_index, progress=progress)
            GLib.idle_add(self._stories_done, errors)

        threading.Thread(target=worker, name="parley-stories", daemon=True).start()

    def _update_progress(self, fraction: float, position: int, count: int, title: str) -> bool:
        self.stories_progress.set_fraction(fraction)
        self.stories_progress.set_text(f"{position}/{count} — {title}")
        return False

    def _stories_done(self, errors: list[str]) -> bool:
        self.download_button.set_sensitive(True)
        self.stories_progress.set_visible(False)
        if errors:
            self.stories_status.set_label(errors[0])
            self.stories_status.add_css_class("error-text")
        else:
            self.stories_status.remove_css_class("error-text")
            self._refresh_stories_index()
        return False

    def _remove_stories(self) -> None:
        stories.remove_all()
        self._refresh_stories_index()

    # -- diagnostics -----------------------------------------------------
    def _diagnostics_card(self) -> Gtk.Box:
        outer, inner = card(self.state.t("diagnostics"))
        inner.append(
            label(f"{self.state.t('version')} {__version__}", "muted", wrap=True)
        )
        inner.append(button(self.state.t("diagnostics"), "ghost", self._show_diagnostics))
        return outer

    def _show_diagnostics(self) -> None:
        dialog = Gtk.Window()
        dialog.set_modal(True)
        dialog.set_transient_for(self.window)
        dialog.set_title(self.state.t("diagnostics"))
        dialog.set_default_size(780, 620)

        view = Gtk.TextView()
        view.set_editable(False)
        view.set_cursor_visible(False)
        view.set_monospace(True)
        view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        view.set_left_margin(10)
        view.set_right_margin(10)
        view.set_top_margin(10)
        view.set_bottom_margin(10)
        view.add_css_class("diagnostics")
        view.get_buffer().set_text(environment_report())

        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scroll.set_hexpand(True)
        scroll.set_vexpand(True)
        scroll.set_child(view)

        actions = horizontal(0)
        actions.set_halign(Gtk.Align.END)
        actions.append(button(self.state.t("close"), "ghost", dialog.destroy))

        box = vertical(10, 16)
        box.set_vexpand(True)
        box.append(scroll)
        box.append(actions)
        dialog.set_child(box)
        dialog.present()
