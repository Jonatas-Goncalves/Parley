"""First-run setup: backend and model selection."""

from __future__ import annotations

import threading

import gi

gi.require_version("Gtk", "4.0")

from gi.repository import GLib, Gtk

from ...core.backends import RUNTIME
from ...core.hardware import detect
from ...core.model_manager import catalog, installed_tiers, recommend
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


class OnboardingPage(Gtk.Box):
    def __init__(self, window, state) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.window = window
        self.state = state
        self.profile = detect()
        self.backend = state.backend
        self.tier = recommend(self.profile).tier
        self._tier_buttons: dict[str, Gtk.ToggleButton] = {}
        self._install_labels: dict[str, Gtk.Label] = {}
        self._installed: dict[str, bool] = {}

        body = page_body()
        body.append(label(state.t("onboarding_title"), "hero-title", wrap=True))
        body.append(label(state.t("onboarding_intro"), "muted", wrap=True))
        body.append(label(self.profile.summary, "pill pill-beginner"))
        body.append(self._backend_card())
        body.append(self._model_card())
        body.append(self._start_row())
        self.append(page_scroll(body))
        self._refresh_installed()

    def _backend_card(self) -> Gtk.Box:
        outer, inner = card(self.state.t("ai_backend"))
        row = horizontal(8)
        self.ollama_button = Gtk.ToggleButton(label="Ollama")
        self.llamacpp_button = Gtk.ToggleButton(label="llama.cpp")
        self.ollama_button.set_hexpand(True)
        self.llamacpp_button.set_hexpand(True)
        self.llamacpp_button.set_group(self.ollama_button)
        (self.llamacpp_button if self.backend == "llamacpp" else self.ollama_button).set_active(True)
        self.ollama_button.connect("toggled", self._backend_changed)
        self.llamacpp_button.connect("toggled", self._backend_changed)
        row.append(self.ollama_button)
        row.append(self.llamacpp_button)
        inner.append(row)
        inner.append(
            label(
                "Ollama is the easiest option. llama.cpp is lighter and uses "
                "GGUF files downloaded by Parley.",
                "card-subtitle",
                wrap=True,
            )
        )
        return outer

    def _model_card(self) -> Gtk.Box:
        outer, inner = card(self.state.t("ai_model"))
        first = None
        for spec in catalog():
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=14)
            toggle = Gtk.ToggleButton()
            toggle.add_css_class("scenario")
            toggle.set_hexpand(True)
            if first is None:
                first = toggle
            else:
                toggle.set_group(first)
            if spec.tier == self.tier:
                toggle.set_active(True)
            toggle.connect("toggled", lambda widget, tier=spec.tier: self._tier_changed(widget, tier))
            self._tier_buttons[spec.tier] = toggle

            text = vertical(2)
            text.set_hexpand(True)
            header = horizontal(8)
            header.append(label(spec.label, "card-title"))
            if spec.tier == recommend(self.profile).tier:
                header.append(label(self.state.t("recommended"), "pill pill-beginner"))
            installed = label("", "card-subtitle")
            self._install_labels[spec.tier] = installed
            header.append(installed)
            text.append(header)
            text.append(
                label(
                    f"{spec.size_gb:.1f} GB · RAM ≥ {spec.min_ram_gb:.0f} GB — {spec.description}",
                    "card-subtitle",
                    wrap=True,
                )
            )
            toggle.set_child(text)
            row.append(toggle)
            inner.append(row)
        return outer

    def _start_row(self) -> Gtk.Box:
        row = horizontal(8)
        row.set_halign(Gtk.Align.END)
        row.set_margin_top(8)
        row.append(button(self.state.t("get_started"), "primary", self._start))
        return row

    def _backend_changed(self, widget) -> None:
        if not widget.get_active():
            return
        self.backend = "llamacpp" if self.llamacpp_button.get_active() else "ollama"

    def _tier_changed(self, widget, tier: str) -> None:
        if widget.get_active():
            self.tier = tier

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
            target=worker, name="parley-onboarding-model-check", daemon=True
        ).start()

    def _apply_installed(self, result: dict[str, bool]) -> bool:
        if not isinstance(result, dict):
            return False
        self._installed = dict(result)
        for tier, widget in self._install_labels.items():
            installed = self._installed.get(tier)
            if installed is None:
                widget.set_label("")
                continue
            widget.set_label(
                self.state.t("model_installed")
                if installed
                else self.state.t("model_not_downloaded")
            )
        return False

    def _start(self) -> None:
        if self._installed.get(self.tier) is True:
            self._finish_start()
            return
        spec = next(
            (item for item in catalog() if item.tier == self.tier),
            catalog()[0],
        )
        self._last_confirm = confirm_dialog(
            self.window,
            self.state.t("model_download_title"),
            self.state.t(
                "model_download_confirm",
                tier=self.state.t(f"model_{self.tier}"),
                model=spec.label,
                size=f"{spec.size_gb:.1f}",
            ),
            self.state.t("download"),
            self._finish_start,
            cancel=self.state.t("cancel"),
        )

    def _finish_start(self) -> None:
        self.state.save(
            onboarding_done=True,
            backend=self.backend,
            backend_explicit=True,
            model_tier=self.tier,
            model="",
            base_url="",
        )
        try:
            RUNTIME.stop()
        except Exception:
            pass
        self.state.start_runtime()
        self.window.show_page("welcome", push_history=False)
