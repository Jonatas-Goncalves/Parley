"""Reusable GTK 4 widgets and helpers for the Parley interface."""

from __future__ import annotations

import re

import gi

gi.require_version("Gtk", "4.0")

from gi.repository import GLib, Gtk, Pango

FLAGS = {
    "pt": "🇧🇷",
    "en": "🇬🇧",
    "es": "🇪🇸",
    "fr": "🇫🇷",
    "it": "🇮🇹",
    "zh": "🇨🇳",
    "ko": "🇰🇷",
    "ja": "🇯🇵",
}

NATIVE_NAMES = {
    "pt": "Português",
    "en": "English",
    "es": "Español",
    "fr": "Français",
    "it": "Italiano",
    "zh": "中文",
    "ko": "한국어",
    "ja": "日本語",
}


def language_button_label(code: str) -> str:
    return f"{FLAGS.get(code, '🌐')}  {NATIVE_NAMES.get(code, code)}"


def scrolled(child: Gtk.Widget, spacing: int = 0) -> Gtk.ScrolledWindow:
    window = Gtk.ScrolledWindow()
    window.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
    window.set_hexpand(True)
    window.set_vexpand(True)
    if spacing:
        child.set_margin_top(spacing)
    window.set_child(child)
    return window


def label(
    text: str = "",
    css: str | None = None,
    wrap: bool = False,
    align: Gtk.Align = Gtk.Align.START,
    markup: bool = False,
) -> Gtk.Label:
    widget = Gtk.Label(label=text)
    widget.set_halign(align)
    widget.set_xalign(0.0 if align == Gtk.Align.START else 0.5)
    if wrap:
        widget.set_wrap(True)
        widget.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
        widget.set_max_width_chars(64)
    if markup:
        widget.set_markup(text)
    if css:
        widget.add_css_class(css)
    return widget


def theme_color(widget: Gtk.Widget, name: str, fallback: str) -> str:
    """Resolve a palette name such as ``parley_good`` to a hex colour."""

    try:
        found, rgba = widget.get_style_context().lookup_color(name)
    except Exception:
        found = False
    if not found:
        return fallback
    red = round(max(0.0, min(1.0, rgba.red)) * 255)
    green = round(max(0.0, min(1.0, rgba.green)) * 255)
    blue = round(max(0.0, min(1.0, rgba.blue)) * 255)
    return f"#{red:02x}{green:02x}{blue:02x}"


def word_markup(widget: Gtk.Widget, text: str, correct: bool) -> str:
    """Return Pango markup that colours a word green or red.

    GTK labels do not accept CSS classes inside markup, so the theme colours
    are resolved from the widget style context and written as foreground
    attributes. This keeps the colours readable in both themes.
    """

    name = "parley_good" if correct else "parley_bad"
    fallback = "#146c43" if correct else "#b42318"
    color = theme_color(widget, name, fallback)
    escaped = GLib.markup_escape_text(str(text))
    return f'<span foreground="{color}" weight="bold">{escaped}</span>'


def muted_markup(widget: Gtk.Widget, text: str) -> str:
    color = theme_color(widget, "parley_muted", "#465266")
    escaped = GLib.markup_escape_text(str(text))
    return f'<span foreground="{color}">{escaped}</span>'


def note_markup(text: str) -> str:
    """Render the small amount of Markdown used by vocabulary notes."""

    escaped = GLib.markup_escape_text(text or "")
    escaped = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", escaped, flags=re.DOTALL)
    escaped = re.sub(r"(?m)^\s*[-*•]\s+", "•  ", escaped)
    return escaped


def vertical(spacing: int = 12, margin: int = 0) -> Gtk.Box:
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=spacing)
    if margin:
        box.set_margin_top(margin)
        box.set_margin_bottom(margin)
        box.set_margin_start(margin)
        box.set_margin_end(margin)
    return box


def horizontal(spacing: int = 8) -> Gtk.Box:
    return Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=spacing)


def button(text: str, css: str | None = None, on_click=None) -> Gtk.Button:
    widget = Gtk.Button(label=text)
    if css:
        for name in css.split():
            widget.add_css_class(name)
    if on_click:
        widget.connect("clicked", lambda *_: on_click())
    return widget


def icon_button(icon_name: str, on_click=None, tooltip: str = "") -> Gtk.Button:
    widget = Gtk.Button.new_from_icon_name(icon_name)
    widget.set_tooltip_text(tooltip or icon_name)
    if on_click:
        widget.connect("clicked", lambda *_: on_click())
    return widget


def page_header(title: str, subtitle: str = "") -> Gtk.Box:
    box = vertical(4)
    box.set_margin_bottom(8)
    box.append(label(title, "section-title", wrap=True))
    if subtitle:
        box.append(label(subtitle, "muted", wrap=True))
    return box


def page_body() -> Gtk.Box:
    box = vertical(16)
    box.set_margin_top(22)
    box.set_margin_bottom(28)
    box.set_margin_start(28)
    box.set_margin_end(28)
    box.set_hexpand(True)
    return box


def centered(box: Gtk.Widget, max_width: int = 760) -> Gtk.Widget:
    holder = vertical(0)
    holder.set_halign(Gtk.Align.CENTER)
    holder.set_hexpand(False)
    holder.set_size_request(max_width, -1)
    holder.append(box)
    return holder


def card(title: str = "", subtitle: str = "") -> tuple[Gtk.Box, Gtk.Box]:
    outer = vertical(8)
    outer.add_css_class("card")
    inner = vertical(10)
    if title:
        inner.append(label(title, "card-title", wrap=True))
    if subtitle:
        inner.append(label(subtitle, "card-subtitle", wrap=True))
    outer.append(inner)
    return outer, inner


def confirm_dialog(
    parent,
    title: str,
    body: str,
    accept: str,
    on_accept,
    cancel: str = "Cancel",
    on_cancel=None,
) -> None:
    dialog = Gtk.Window()
    dialog.set_modal(True)
    dialog.set_transient_for(parent)
    dialog.set_title(title)
    dialog.set_default_size(420, -1)
    dialog.set_resizable(False)

    content = vertical(16, 20)
    content.append(label(title, "section-title", wrap=True))
    content.append(label(body, "muted", wrap=True))
    actions = horizontal(8)
    actions.set_halign(Gtk.Align.END)
    accepted = False

    def close() -> None:
        dialog.destroy()

    def accept_action() -> None:
        nonlocal accepted
        accepted = True
        close()
        on_accept()

    def cancel_action() -> None:
        close()
        if on_cancel is not None:
            on_cancel()

    def on_close(*_args) -> bool:
        if not accepted and on_cancel is not None:
            on_cancel()
        return False

    dialog.connect("close-request", on_close)
    actions.append(button(cancel, "ghost", cancel_action))
    actions.append(button(accept, "primary", accept_action))
    content.append(actions)
    dialog.set_child(content)
    dialog.present()
    return dialog


def update_state_dot(dot: Gtk.Widget, state: str) -> None:
    for name in ("listening", "thinking", "speaking", "paused", "error"):
        dot.remove_css_class(name)
    dot.add_css_class(state if state in ("listening", "thinking", "speaking", "paused", "error") else "paused")


def page_scroll(body: Gtk.Widget, max_width: int = 780) -> Gtk.ScrolledWindow:
    holder = centered(body, max_width=max_width)
    holder.set_vexpand(True)
    scroll = Gtk.ScrolledWindow()
    scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
    scroll.set_child(holder)
    scroll.set_vexpand(True)
    scroll.set_hexpand(True)
    return scroll
