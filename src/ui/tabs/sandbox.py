"""Sandbox options tab composition."""

from __future__ import annotations

import os
from pathlib import Path

from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.widgets import Input, Label

from detection import detect_dbus_session, detect_display_server
from model import DesktopConfig, NamespaceConfig, NetworkConfig, ProcessConfig
from ui.widgets import OptionCard


def compose_sandbox_tab() -> ComposeResult:
    """Compose the sandbox options tab content.

    Yields:
        Textual widgets for the sandbox tab
    """
    with VerticalScroll(id="sandbox-tab-content"):
        with Horizontal(id="options-grid"):
            with Vertical(classes="options-column"):
                with Container(classes="options-section"):
                    yield Label("Isolation", classes="section-label")
                    yield OptionCard(NamespaceConfig.unshare_user)
                    with Container(id="uid-gid-options", classes="hidden"):
                        yield Label("UID:")
                        yield Input(value=str(os.getuid()), id="opt-uid")
                        yield Label("GID:")
                        yield Input(value=str(os.getgid()), id="opt-gid")
                    yield OptionCard(NamespaceConfig.unshare_pid)
                    yield OptionCard(NamespaceConfig.unshare_ipc)
                    yield OptionCard(NamespaceConfig.unshare_uts)
                    yield OptionCard(NamespaceConfig.unshare_cgroup)
                    yield OptionCard(NamespaceConfig.disable_userns)
                with Container(classes="options-section"):
                    yield Label("Process", classes="section-label")
                    yield OptionCard(ProcessConfig.die_with_parent)
                    yield OptionCard(ProcessConfig.new_session)
                    yield OptionCard(ProcessConfig.as_pid_1)
                    yield Label("Working dir:")
                    yield Input(value=str(Path.cwd()), id="opt-chdir")
                    yield Label("Custom hostname:")
                    yield Input(placeholder="sandbox", id="opt-hostname")
            with Vertical(classes="options-column"):
                with Container(classes="options-section"):
                    yield Label("Network", classes="section-label")
                    yield OptionCard(NetworkConfig.share_net)
                    yield OptionCard(NetworkConfig.bind_resolv_conf)
                    yield OptionCard(NetworkConfig.bind_ssl_certs)
                with Container(classes="options-section"):
                    yield Label("Desktop Integration", classes="section-label")
                    # Detect what's available
                    display_info = detect_display_server()
                    dbus_paths = detect_dbus_session()
                    dbus_desc = (
                        DesktopConfig.allow_dbus.explanation
                        if dbus_paths
                        else "Not detected"
                    )
                    yield OptionCard(DesktopConfig.allow_dbus, explanation=dbus_desc)
                    if display_info["type"] == "wayland":
                        display_desc = "Wayland display access"
                    elif display_info["type"] == "x11":
                        display_desc = "X11 display access"
                    elif display_info["type"] == "both":
                        display_desc = "X11 + Wayland display access"
                    else:
                        display_desc = "No display detected"
                    yield OptionCard(DesktopConfig.allow_display, explanation=display_desc)
                    yield OptionCard(DesktopConfig.bind_user_config)
