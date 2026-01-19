"""Sandbox options tab composition."""

from __future__ import annotations

import os
from pathlib import Path

from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.widgets import Input, Label

from detection import detect_dbus_session, detect_display_server
from model import groups
from ui.widgets import OptionCard


def compose_sandbox_tab() -> ComposeResult:
    """Compose the sandbox options tab content.

    Yields:
        Textual widgets for the sandbox tab
    """
    with VerticalScroll(id="sandbox-tab-content"):
        with Horizontal(id="options-grid"):
            # Left column: Isolation + Process
            with Vertical(classes="options-column"):
                with Container(classes="options-section"):
                    yield Label(groups.isolation_group.title, classes="section-label")
                    yield OptionCard(groups.unshare_user)
                    with Container(id="uid-gid-options", classes="hidden"):
                        yield Label("UID:")
                        yield Input(value=str(os.getuid()), id="opt-uid")
                        yield Label("GID:")
                        yield Input(value=str(os.getgid()), id="opt-gid")
                    yield OptionCard(groups.unshare_pid)
                    yield OptionCard(groups.unshare_ipc)
                    yield OptionCard(groups.unshare_uts)
                    yield OptionCard(groups.unshare_cgroup)
                    yield OptionCard(groups.disable_userns)
                with Container(classes="options-section"):
                    yield Label(groups.process_group.title, classes="section-label")
                    yield OptionCard(groups.die_with_parent)
                    yield OptionCard(groups.new_session)
                    yield OptionCard(groups.as_pid_1)
                    yield Label("Working dir:")
                    yield Input(value=str(Path.cwd()), id="opt-chdir")
                    yield Label("Custom hostname:")
                    yield Input(placeholder="sandbox", id="opt-hostname")

            # Right column: Network + Desktop
            with Vertical(classes="options-column"):
                with Container(classes="options-section"):
                    yield Label(groups.network_group.title, classes="section-label")
                    yield OptionCard(groups.share_net)
                    yield OptionCard(groups.bind_resolv_conf)
                    yield OptionCard(groups.bind_ssl_certs)
                with Container(classes="options-section"):
                    yield Label(groups.desktop_group.title, classes="section-label")
                    # Detect what's available
                    display_info = detect_display_server()
                    dbus_paths = detect_dbus_session()
                    dbus_desc = (
                        groups.allow_dbus.explanation
                        if dbus_paths
                        else "Not detected"
                    )
                    yield OptionCard(groups.allow_dbus, explanation=dbus_desc)
                    if display_info["type"] == "wayland":
                        display_desc = "Wayland display access"
                    elif display_info["type"] == "x11":
                        display_desc = "X11 display access"
                    elif display_info["type"] == "both":
                        display_desc = "X11 + Wayland display access"
                    else:
                        display_desc = "No display detected"
                    yield OptionCard(groups.allow_display, explanation=display_desc)
                    yield OptionCard(groups.bind_user_config)
