"""Sandbox options tab composition."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.widgets import Input, Label, Static

from detection import detect_dbus_session, detect_display_server
from model import groups
from ui.widgets import DevModeCard, OptionCard


def compose_sandbox_tab(on_dev_mode_change: Callable[[str], None]) -> ComposeResult:
    """Compose the sandbox options tab content.

    Args:
        on_dev_mode_change: Callback when /dev mode is changed

    Yields:
        Textual widgets for the sandbox tab
    """
    with VerticalScroll(id="sandbox-tab-content"):
        with Horizontal(id="options-grid"):
            # Left column: User + Desktop + Virtual Filesystems
            with Vertical(classes="options-column"):
                # User card - always visible with progressive disclosure
                with Container(classes="options-section"):
                    yield Label(groups.user_group.title, classes="section-label")
                    yield OptionCard(groups.unshare_user)
                    with Container(id="uid-gid-options", classes="hidden"):
                        yield Label("UID:")
                        yield Input(value="0", id="opt-uid")
                        yield Label("GID:")
                        yield Input(value="0", id="opt-gid")
                    with Container(id="username-options", classes="hidden"):
                        yield Label("Username:")
                        yield Input(value="", id="opt-username", placeholder="e.g., appuser")
                    with Container(id="virtual-user-options", classes="hidden"):
                        yield OptionCard(groups.synthetic_passwd)
                        yield OptionCard(groups.overlay_home)
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
                with Container(classes="options-section"):
                    yield Label(groups.vfs_group.title, classes="section-label")
                    yield DevModeCard(on_dev_mode_change)
                    yield OptionCard(groups.mount_proc)
                    yield OptionCard(groups.mount_tmp)
                    yield Label("Tmpfs size:")
                    yield Input(placeholder="default (half of RAM)", id="opt-tmpfs-size")

            # Right column: Isolation + Process
            with Vertical(classes="options-column"):
                with Container(classes="options-section"):
                    yield Label(groups.isolation_group.title, classes="section-label")
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
