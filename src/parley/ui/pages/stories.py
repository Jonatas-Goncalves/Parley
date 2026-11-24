"""Spoken Stories player."""

from __future__ import annotations

import threading

import gi

gi.require_version("Gtk", "4.0")

from gi.repository import GLib, Gtk

from ...content import stories
from ..helpers import (
    confirm_dialog,
    label,
    page_body,
    page_scroll,
    vertical,
)
from ..widgets.audio_bar import AudioBar


class StoriesPage(Gtk.Box):
    def __init__(self, window, state) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.window = window
        self.state = state
        self.index = stories.scan_local()
        self.remote_index = self.index
        self.selected = 0
        self._confirm = None
        self._rows: list[Gtk.ListBoxRow] = []

        body = page_body()
        body.append(label(state.t("stories_title"), "hero-title", wrap=True))

        self.summary = label("", "muted", wrap=True)
        body.append(self.summary)

        self.audio = AudioBar()
        body.append(self.audio)

        self.listbox = Gtk.ListBox()
        self.listbox.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.listbox.connect("row-selected", self._row_selected)
        self.listbox.add_css_class("card")
        body.append(self.listbox)

        self.empty_label = label(state.t("stories_missing"), "muted", wrap=True)
        body.append(self.empty_label)

        self.download_button = Gtk.Button(label=state.t("stories_download"))
        self.download_button.add_css_class("primary")
        self.download_button.connect("clicked", lambda *_: self._ask_download())
        body.append(self.download_button)

        self.append(page_scroll(body, max_width=860))
        self._refresh()
        self._refresh_remote()

    # -- content ---------------------------------------------------------
    def _refresh(self) -> None:
        self.index = stories.scan_local()
        while True:
            row = self.listbox.get_row_at_index(0)
            if row is None:
                break
            self.listbox.remove(row)

        for story in self.index.stories:
            path = stories.resolved_path(story)
            row = Gtk.ListBoxRow()
            row.add_css_class("story-row")
            box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
            box.set_margin_top(4)
            box.set_margin_bottom(4)
            text = vertical(2)
            text.set_hexpand(True)
            text.append(label(story.title, "story-title", wrap=True))
            author = story.author or self.state.t("spoken_stories")
            text.append(label(author, "muted"))
            box.append(text)
            duration = f"{int(story.seconds) // 60}:{int(story.seconds) % 60:02d}"
            box.append(label(duration if story.seconds else "—", "muted"))
            row.set_child(box)
            row.story = story
            row.available = path is not None
            self.listbox.append(row)

        available = sum(1 for story in self.index.stories if stories.resolved_path(story))
        self.summary.set_text(
            self.state.t("stories_installed")
            + f"  ·  {available}"
        )
        self.empty_label.set_visible(self.index.count == 0)
        if self.index.count == 0:
            self.empty_label.set_text(self.state.t("stories_missing"))
        if self.index.count and self.listbox.get_row_at_index(self.selected) is not None:
            self.listbox.select_row(self.listbox.get_row_at_index(self.selected))

    def _refresh_remote(self) -> None:
        def worker() -> None:
            try:
                index = stories.remote_index()
            except Exception:
                index = stories.load_index()
            GLib.idle_add(self._apply_remote, index)

        threading.Thread(target=worker, name="parley-stories-remote", daemon=True).start()

    def _apply_remote(self, index) -> bool:
        self.remote_index = index
        local_names = {s.filename for s in self.index.stories}
        missing = [s for s in index.stories if s.filename not in local_names]
        self.download_button.set_visible(bool(missing))
        return False

    def _row_selected(self, _listbox, row) -> None:
        if row is None:
            return
        self.selected = row.get_index()
        if not getattr(row, "available", False):
            self.audio.stop()
            return
        path = stories.resolved_path(row.story)
        if path is not None:
            self.audio.load(path)
            self.audio.play()

    def shutdown(self) -> None:
        self.audio.stop()

    def _ask_download(self) -> None:
        local_names = {s.filename for s in self.index.stories}
        missing = [s for s in self.remote_index.stories if s.filename not in local_names]
        target = stories.StoryIndex(missing) if missing else self.remote_index
        text = self.state.t(
            "stories_download_confirm",
            count=target.count,
            size=f"{target.total_megabytes:.1f}",
        )
        self._pending_download = target
        self._confirm = confirm_dialog(
            self.window,
            self.state.t("stories_download"),
            text,
            self.state.t("stories_download"),
            self._download,
        )

    def _download(self) -> None:
        import threading

        from gi.repository import GLib

        target = getattr(self, "_pending_download", self.remote_index)
        self.download_button.set_sensitive(False)
        self.summary.set_text(self.state.t("loading"))

        def progress(position, count, done, total, title) -> None:
            GLib.idle_add(
                self.summary.set_text,
                f"{position}/{count} — {title}",
            )

        def worker() -> None:
            errors = stories.download(target, progress=progress)
            GLib.idle_add(self._downloaded, errors)

        threading.Thread(target=worker, name="parley-stories", daemon=True).start()

    def _downloaded(self, errors: list[str]) -> bool:
        self.download_button.set_sensitive(True)
        if errors:
            self.summary.set_text(errors[0])
        self._refresh()
        self._refresh_remote()
        return False
