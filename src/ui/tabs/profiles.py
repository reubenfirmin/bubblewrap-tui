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
        with Container(id="save-profile-section"):
            yield Label("Save Current Config", classes="section-label")
            with Horizontal(id="save-profile-row"):
                yield Input(placeholder="Profile name...", id="profile-name-input")
                yield Button("Save", id="save-profile-btn", variant="success")
        with Container(id="load-profile-section"):
            yield Label("Load from Path", classes="section-label")
            with Horizontal(id="load-profile-row"):
                yield Input(placeholder="Path to profile...", id="load-profile-path")
                yield Button("Load", id="load-profile-btn", variant="primary")
