"""UIField definitions for Desktop Integration group."""

from pathlib import Path

from model.ui_field import UIField


def _named(name: str, field: UIField) -> UIField:
    """Set the name attribute on a UIField and return it."""
    field.name = name
    return field


allow_dbus = _named("allow_dbus", UIField(
    bool, False, "opt-dbus",
    "D-Bus session", "Open browser, notifications, etc.",
    # bwrap_args handled by group's custom to_args
))

allow_display = _named("allow_display", UIField(
    bool, False, "opt-display",
    "Display server", "X11/Wayland display access",
    # bwrap_args handled by group's custom to_args
))

bind_user_config = _named("bind_user_config", UIField(
    bool, False, "opt-user-config",
    "~/.config", "App settings - use caution",
    # bwrap_args handled via bound_dirs sync in Quick Shortcuts
))
bind_user_config.shortcut_path = Path.home() / ".config"
