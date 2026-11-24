"""Reusable audio player bar with seek and speed control."""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")

from gi.repository import GLib, Gtk

from ...audio import AudioPlayer
from ..helpers import horizontal, label

SPEEDS = (0.5, 0.75, 1.0, 1.25, 1.5)


def _clock(seconds: float) -> str:
    seconds = max(0, int(seconds))
    return f"{seconds // 60}:{seconds % 60:02d}"


class AudioBar(Gtk.Box):
    def __init__(self, on_finished=None) -> None:
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        self.add_css_class("card")
        self._updating = False
        self._path = None
        self.player = AudioPlayer()
        self.player.on_position = self._on_position
        self.player.on_done = lambda: GLib.idle_add(self._on_done)
        self._on_finished = on_finished

        self.play_button = Gtk.Button(label="▶")
        self.play_button.add_css_class("ghost")
        self.play_button.set_tooltip_text("Play")
        self.play_button.connect("clicked", lambda *_: self._toggle())
        self.append(self.play_button)

        self.scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 100, 1)
        self.scale.set_draw_value(False)
        self.scale.set_hexpand(True)
        self.scale.set_sensitive(False)
        self.scale.connect("value-changed", self._on_scale_changed)
        self.append(self.scale)

        self.time_label = label("0:00 / 0:00", "muted")
        self.append(self.time_label)

        speed_row = horizontal(4)
        self.speed_button = Gtk.MenuButton(label="1×")
        self.speed_button.add_css_class("ghost")
        speed_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        for speed in SPEEDS:
            option = Gtk.Button(label=f"{speed:g}×")
            option.add_css_class("flat")
            option.connect("clicked", lambda _w, speed=speed: self._set_speed(speed))
            speed_box.append(option)
        popover = Gtk.Popover()
        popover.set_child(speed_box)
        self.speed_button.set_popover(popover)
        speed_row.append(self.speed_button)
        self.append(speed_row)

    # -- public ----------------------------------------------------------
    def load(self, path) -> None:
        self._path = path
        duration = self.player.load(path)
        self._updating = True
        self.scale.set_range(0, max(1.0, duration))
        self.scale.set_value(0)
        self._updating = False
        self.scale.set_sensitive(duration > 0)
        self.time_label.set_label(f"0:00 / {_clock(duration)}")
        self.play_button.set_label("▶")

    def play(self) -> None:
        if self._path is None:
            return
        duration = self.player.duration
        if duration > 0 and self.player.position >= duration - 0.05:
            self._updating = True
            self.scale.set_value(0)
            self._updating = False
            self.time_label.set_label(f"0:00 / {_clock(duration)}")
        self.player.play()
        self.play_button.set_label("⏸")

    def pause(self) -> None:
        self.player.pause()
        self.play_button.set_label("▶")

    def stop(self) -> None:
        self.player.stop()
        self.play_button.set_label("▶")
        self._updating = True
        self.scale.set_value(0)
        self._updating = False

    def seek(self, seconds: float) -> None:
        self.player.seek(seconds)

    # -- callbacks -------------------------------------------------------
    def _toggle(self) -> None:
        if self.player.playing:
            self.pause()
        else:
            self.play()

    def _set_speed(self, speed: float) -> None:
        self.player.set_speed(speed)
        self.speed_button.set_label(f"{speed:g}×")
        popover = self.speed_button.get_popover()
        if popover is not None:
            popover.popdown()

    def _on_scale_changed(self, scale) -> None:
        if self._updating:
            return
        self.seek(scale.get_value())

    def _on_position(self, position: float, duration: float) -> None:
        GLib.idle_add(self._update_ui, position, duration)

    def _update_ui(self, position: float, duration: float) -> bool:
        self._updating = True
        self.scale.set_value(position)
        self._updating = False
        self.time_label.set_label(f"{_clock(position)} / {_clock(duration)}")
        if self.player.playing:
            self.play_button.set_label("⏸")
        return False

    def _on_done(self) -> bool:
        self.play_button.set_label("▶")
        if self._on_finished:
            self._on_finished()
        return False
