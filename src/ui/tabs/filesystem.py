"""File Systems tab composition."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.widgets import Input, Label

from model import FilesystemConfig
from ui.widgets import DevModeCard, OptionCard


def compose_filesystem_tab(on_dev_mode_change: Callable[[str], None]) -> ComposeResult:
    """Compose the file systems tab content.

    Args:
        on_dev_mode_change: Callback when /dev mode is changed

    Yields:
        Textual widgets for the file systems tab
    """
    with VerticalScroll(id="filesystems-tab-content"):
        with Horizontal(id="options-grid"):
            with Vertical(classes="options-column"):
                with Container(classes="options-section"):
                    yield Label("Virtual Filesystems", classes="section-label")
                    yield DevModeCard(on_dev_mode_change)
                    yield OptionCard(FilesystemConfig.mount_proc)
                    yield OptionCard(FilesystemConfig.mount_tmp)
                    yield Label("Tmpfs size:")
                    yield Input(placeholder="default (half of RAM)", id="opt-tmpfs-size")
            with Vertical(classes="options-column"):
                with Container(classes="options-section"):
                    yield Label("System Paths (read-only)", classes="section-label")
                    yield OptionCard(FilesystemConfig.bind_usr)
                    yield OptionCard(FilesystemConfig.bind_bin)
                    yield OptionCard(FilesystemConfig.bind_lib)
                    yield OptionCard(FilesystemConfig.bind_lib64, default=Path("/lib64").exists())
                    yield OptionCard(FilesystemConfig.bind_sbin)
                    yield OptionCard(FilesystemConfig.bind_etc)
