"""Overlays tab composition."""

from __future__ import annotations

from pathlib import Path

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import Button, Static


def compose_overlays_tab() -> ComposeResult:
    """Compose the overlays tab content.

    Yields:
        Textual widgets for the overlays tab
    """
    with Vertical(id="overlays-tab-content"):
        home = str(Path.home())
        yield Static(
            "Click mode button to cycle: tmpfs → overlay → persist\n\n"
            "  tmpfs      Empty writable directory (no source needed)\n"
            "  overlay    Writable layer on existing dir, changes in RAM\n"
            "  persist    Writable layer on existing dir, changes saved to disk\n\n"
            "Examples:\n"
            f"  tmpfs, mount={home} → isolated home, starts empty\n"
            "  overlay, source=/etc, mount=/etc → writable /etc, real files as base",
            id="overlay-hint",
        )
        yield Button("+ Add Overlay", id="add-overlay-btn", variant="success")
        with Horizontal(id="overlay-header", classes="hidden"):
            yield Static("Mode", classes="overlay-header-mode")
            yield Static("Source (real directory)", classes="overlay-header-src")
            yield Static("", classes="overlay-header-arrow")
            yield Static("Mount point (in sandbox)", classes="overlay-header-dest")
            yield Static("Write dir (persistent only)", classes="overlay-header-write")
            yield Static("", classes="overlay-header-remove")
        yield VerticalScroll(id="overlays-list")
