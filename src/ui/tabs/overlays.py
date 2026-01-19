"""Overlays tab composition."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import Button, Static


def compose_overlays_tab() -> ComposeResult:
    """Compose the overlays tab content.

    Yields:
        Textual widgets for the overlays tab
    """
    with Vertical(id="overlays-tab-content"):
        yield Static(
            "Overlays make directories appear writable without changing originals.\n\n"
            "  tmpfs      Changes discarded on exit\n"
            "  persistent Changes saved to write dir\n\n"
            "Example: source=/usr, mount=/usr, mode=tmpfs\n"
            "         Sandbox can 'install' packages, real /usr untouched.",
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
