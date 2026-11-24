"""Shared application state for the GTK interface."""

from __future__ import annotations

from ..core import startup_state
from ..core.backends import RUNTIME, Snapshot
from ..core.config import MODEL_TIERS, SETTINGS, normalize_language_code
from ..core.i18n import normalize_ui_language, t

THEME_MODES = ("system", "light", "dark")


def detect_system_theme() -> str:
    """Return ``dark`` when the desktop asks for a dark colour scheme."""

    try:
        import gi

        gi.require_version("Gtk", "4.0")

        from gi.repository import Gtk

        settings = Gtk.Settings.get_default()
        if settings is None:
            return "light"
        scheme = getattr(Gtk, "InterfaceColorScheme", None)
        if (
            scheme is not None
            and settings.find_property("gtk-interface-color-scheme") is not None
        ):
            value = settings.get_property("gtk-interface-color-scheme")
            dark_values = {
                getattr(scheme, name)
                for name in ("DARK", "PREFER_DARK")
                if getattr(scheme, name, None) is not None
            }
            if value in dark_values:
                return "dark"
            light_values = {
                getattr(scheme, name)
                for name in ("LIGHT", "PREFER_LIGHT")
                if getattr(scheme, name, None) is not None
            }
            if value in light_values:
                return "light"
        return "dark" if settings.get_property("gtk-application-prefer-dark-theme") else "light"
    except Exception:
        return "light"


class AppState:
    def __init__(self) -> None:
        self.config = startup_state.load()
        self.engine = None
        self.last_scenario_id = str(self.config.get("scenario") or "")
        self._watch_source = 0

    # -- preferences -----------------------------------------------------
    def save(self, **updates: object) -> None:
        self.config = startup_state.save(updates)

    @property
    def ui_language(self) -> str:
        return normalize_ui_language(str(self.config.get("ui_language") or "en"))

    @property
    def theme_mode(self) -> str:
        mode = str(self.config.get("theme") or "system").lower()
        return mode if mode in THEME_MODES else "system"

    @property
    def theme(self) -> str:
        mode = self.theme_mode
        if mode in ("light", "dark"):
            return mode
        return detect_system_theme()

    @property
    def native(self) -> str:
        return normalize_language_code(str(self.config.get("native") or "pt")) or "pt"

    @property
    def target(self) -> str:
        return normalize_language_code(str(self.config.get("target") or "en")) or "en"

    @property
    def backend(self) -> str:
        backend = str(self.config.get("backend") or "ollama").lower()
        return "llamacpp" if backend == "llamacpp" else "ollama"

    @property
    def base_url(self) -> str:
        configured = str(self.config.get("base_url") or "").strip()
        if configured:
            return configured
        return SETTINGS.llama_cpp_url if self.backend == "llamacpp" else SETTINGS.ollama_url

    @property
    def model_tier(self) -> str:
        tier = str(self.config.get("model_tier") or "medium")
        return tier if tier in MODEL_TIERS else "medium"

    @property
    def model(self) -> str:
        configured = str(self.config.get("model") or "").strip()
        if configured:
            return configured
        return MODEL_TIERS[self.model_tier]

    @property
    def custom_gguf_path(self) -> str:
        return str(self.config.get("custom_gguf_path") or "").strip()

    @property
    def voice_mode(self) -> str:
        mode = str(self.config.get("voice_mode") or "continuous")
        return "push_to_talk" if mode == "push_to_talk" else "continuous"

    @property
    def whisper_model(self) -> str:
        return str(self.config.get("whisper_model") or "base")

    @property
    def path(self) -> str:
        """Alias used by the window for the settings button."""

        return "settings"

    def t(self, key: str, **kwargs: object) -> str:
        return t(key, self.ui_language, **kwargs)

    def bool(self, key: str, default: bool = True) -> bool:
        value = self.config.get(key)
        return bool(default if value is None else value)

    # -- backend ---------------------------------------------------------
    def snapshot(self) -> Snapshot:
        return RUNTIME.snapshot()

    def start_runtime(self) -> None:
        RUNTIME.ensure(wait=False)

    def watch_runtime(self, callback) -> None:
        """Call ``callback(snapshot)`` on every change until the engine is ready."""

        from gi.repository import GLib

        if self._watch_source:
            GLib.source_remove(self._watch_source)

        def tick():
            snapshot = RUNTIME.snapshot()
            try:
                callback(snapshot)
            except Exception:
                pass
            if snapshot.state in ("running", "error"):
                self._watch_source = 0
                return False
            return True

        self._watch_source = GLib.timeout_add(500, tick)

    def stop_engine(self) -> None:
        if self.engine is not None:
            try:
                self.engine.stop()
            except Exception:
                pass
            self.engine = None
