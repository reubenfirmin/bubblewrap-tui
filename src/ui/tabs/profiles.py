"""Profiles tab composition."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.widgets import Button, Input, Label


def compose_profiles_tab() -> ComposeResult:
    """Compose the profiles tab content.

    Yields:
        Textual widgets for the profiles tab
    """
    with Vertical(id="profiles-tab-content"):
        yield Label("Saved Profiles", classes="section-label")
        yield VerticalScroll(id="profiles-list")
        with Horizontal(id="save-profile-row"):
            yield Input(placeholder="Profile name...", id="profile-name-input")
            yield Button("Save", id="save-profile-btn", variant="success")
