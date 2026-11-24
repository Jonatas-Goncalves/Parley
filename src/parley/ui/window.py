"""Window shell: header bar, page stack and navigation history."""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")

from gi.repository import Gtk

from .helpers import icon_button
from .pages.level_test import LevelTestPage
from .pages.onboarding import OnboardingPage
from .pages.practice import PracticePage
from .pages.pronunciation import PronunciationPage
from .pages.scenarios import ScenariosPage
from .pages.sentence import SentencePage
from .pages.session import SessionPage
from .pages.settings import SettingsPage
from .pages.stories import StoriesPage
from .pages.welcome import WelcomePage


class ParleyWindow(Gtk.ApplicationWindow):
    def __init__(self, application, state) -> None:
        super().__init__(application=application)
        self.state = state
        self.set_title("Parley")
        self.set_default_size(1060, 760)
        self.set_size_request(760, 560)
        self.add_css_class("parley")

        self.header = Gtk.HeaderBar()
        self.header.add_css_class("parley-header")
        self.header.set_show_title_buttons(True)
        self.set_titlebar(self.header)

        self.title_label = Gtk.Label(label="Parley")
        self.title_label.add_css_class("section-title")
        self.title_label.set_margin_start(10)
        self.header.set_title_widget(self.title_label)

        self.stack = Gtk.Stack()
        self.stack.set_transition_type(Gtk.StackTransitionType.SLIDE_LEFT)
        self.stack.set_transition_duration(220)

        # Back stays over the page, in its top-left corner, instead of sharing
        # the title bar with the window controls. A small gutter keeps it clear
        # of the page heading.
        self.back_button = icon_button("go-previous-symbolic", self.go_back, "Back")
        self.back_button.add_css_class("floating-back")
        self.back_button.set_halign(Gtk.Align.START)
        self.back_button.set_valign(Gtk.Align.START)
        self.back_button.set_margin_start(10)
        self.back_button.set_margin_top(10)
        self.back_button.set_visible(False)

        self.page_overlay = Gtk.Overlay()
        self.page_overlay.set_child(self.stack)
        self.page_overlay.add_overlay(self.back_button)
        self.set_child(self.page_overlay)

        self._history: list[tuple[str, dict]] = []
        self._current: tuple[str, dict] = ("welcome", {})
        self._pages: dict[str, Gtk.Widget] = {}

        self.show_page("welcome", push_history=False)

    # -- navigation ------------------------------------------------------
    def show_page(self, name: str, push_history: bool = True, **kwargs) -> None:
        if push_history and self._current[0] != name:
            self._history.append(self._current)
        elif not push_history and self._current[0] == name:
            self._history.clear()

        self._current = (name, kwargs)
        self._switch(name, kwargs)

    def go_back(self) -> None:
        if not self._history:
            self.show_page("welcome", push_history=False)
            return
        name, kwargs = self._history.pop()
        self._current = (name, kwargs)
        self._switch(name, kwargs)

    def reset_to(self, name: str, **kwargs) -> None:
        """Return to a page with a single Back target, for example after a session."""

        self._history.clear()
        if name != "welcome":
            self._history.append(("welcome", {}))
        self.show_page(name, push_history=False, **kwargs)

    def apply_theme(self) -> None:
        application = self.get_application()
        if application is not None:
            application.apply_theme()

    def _switch(self, name: str, kwargs: dict) -> None:
        previous_name = next(iter(self._pages), None)
        self._teardown_name(previous_name)
        page = self._build(name, **kwargs)
        self.stack.add_named(page, name)
        self._pages = {name: page}
        self.stack.set_visible_child_name(name)
        show_back = name != "welcome"
        self.back_button.set_visible(show_back)
        self.stack.set_margin_start(52 if show_back else 0)
        self.stack.set_margin_top(10 if show_back else 0)
        self.title_label.set_label(self._title_for(name))

    def _teardown_current(self) -> None:
        self._teardown_name(self._current[0])

    def _teardown_name(self, name: str | None) -> None:
        if name is None:
            return
        page = self._pages.pop(name, None)
        if page is None:
            return
        shutdown = getattr(page, "shutdown", None)
        if callable(shutdown):
            try:
                shutdown()
            except Exception:
                pass
        if page.get_parent() is self.stack:
            self.stack.remove(page)

    def refresh(self) -> None:
        """Rebuild the visible page, for example after a language change."""

        name, kwargs = self._current
        self._switch(name, kwargs)

    def shutdown(self) -> None:
        """Stop whatever the visible page is running."""

        self._teardown_current()
        self.state.stop_engine()

    def open_settings(self) -> None:
        self.show_page("settings")

    def _title_for(self, name: str) -> str:
        keys = {
            "welcome": "app_name",
            "onboarding": "onboarding_title",
            "practice": "practice_title",
            "scenarios": "practice_title",
            "session": "voice_practice",
            "pronunciation": "pronunciation",
            "settings": "settings",
            "stories": "spoken_stories",
            "sentence": "complete_sentence",
            "level_test": "level_test_title",
        }
        return self.state.t(keys.get(name, "app_name"))

    def _build(self, name: str, **kwargs) -> Gtk.Widget:
        if name == "welcome":
            return WelcomePage(self, self.state)
        if name == "onboarding":
            return OnboardingPage(self, self.state)
        if name == "practice":
            return PracticePage(self, self.state)
        if name == "scenarios":
            return ScenariosPage(self, self.state, **kwargs)
        if name == "session":
            return SessionPage(self, self.state, **kwargs)
        if name == "pronunciation":
            return PronunciationPage(self, self.state, **kwargs)
        if name == "settings":
            return SettingsPage(self, self.state)
        if name == "stories":
            return StoriesPage(self, self.state)
        if name == "sentence":
            return SentencePage(self, self.state)
        if name == "level_test":
            return LevelTestPage(self, self.state)
        return WelcomePage(self, self.state)
