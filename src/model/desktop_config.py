"""Desktop integration configuration model."""

from model.ui_field import ConfigBase, UIField


class DesktopConfig(ConfigBase):
    """Desktop integration settings for the sandbox."""

    allow_dbus = UIField(
        bool, False, "opt-dbus",
        "D-Bus session", "Open browser, notifications, etc.",
        # bwrap_args handled specially - needs to iterate D-Bus paths
    )
    allow_display = UIField(
        bool, False, "opt-display",
        "Display server", "X11/Wayland display access",
        # bwrap_args handled specially - needs display detection
    )
    bind_user_config = UIField(
        bool, False, "opt-user-config",
        "User config", "~/.config for default apps, themes",
        # bwrap_args handled specially - binds ~/.config
    )
