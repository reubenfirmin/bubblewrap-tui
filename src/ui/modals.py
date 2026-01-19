"""Modal dialogs for profile management."""

from __future__ import annotations

from pathlib import Path

from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, Static

from profiles import Profile, BUI_PROFILES_DIR


class ProfileListItem(Static):
    """A clickable profile list item."""

    def __init__(self, profile: Profile) -> None:
        super().__init__(profile.name)
        self.profile = profile
        self.add_class("profile-list-item")

    def on_click(self) -> None:
        """Handle click - dismiss modal with this profile."""
        self.screen.dismiss(self.profile.path)


class LoadProfileModal(ModalScreen[Path | None]):
    """Modal for loading a saved profile."""

    BINDINGS = [("escape", "cancel", "Cancel")]

    def compose(self) -> ComposeResult:
        with Vertical(id="load-profile-modal"):
            yield Label("Load Profile", id="modal-title")
            with VerticalScroll(id="modal-profile-list"):
                profiles = Profile.list_profiles(BUI_PROFILES_DIR)
                if profiles:
                    for profile in profiles:
                        yield ProfileListItem(profile)
                else:
                    yield Static("No saved profiles", id="no-profiles")
            with Horizontal(id="modal-buttons"):
                yield Button("Cancel", id="cancel-btn", variant="default")

    def action_cancel(self) -> None:
        self.dismiss(None)

    @on(Button.Pressed, "#cancel-btn")
    def on_cancel(self, event: Button.Pressed) -> None:
        self.dismiss(None)


class SaveProfileModal(ModalScreen[str | None]):
    """Modal for saving current config as a profile."""

    BINDINGS = [("escape", "cancel", "Cancel")]

    def compose(self) -> ComposeResult:
        with Vertical(id="save-profile-modal"):
            yield Label("Save Profile", id="modal-title")
            yield Input(placeholder="Profile name...", id="profile-name-input")
            with Horizontal(id="modal-buttons"):
                yield Button("Cancel", id="cancel-btn", variant="default")
                yield Button("Save", id="save-btn", variant="success")

    def on_mount(self) -> None:
        self.query_one("#profile-name-input", Input).focus()

    def action_cancel(self) -> None:
        self.dismiss(None)

    @on(Button.Pressed, "#cancel-btn")
    def on_cancel(self, event: Button.Pressed) -> None:
        self.dismiss(None)

    @on(Button.Pressed, "#save-btn")
    def on_save(self, event: Button.Pressed) -> None:
        name = self.query_one("#profile-name-input", Input).value.strip()
        if name:
            self.dismiss(name)

    @on(Input.Submitted, "#profile-name-input")
    def on_input_submitted(self, event: Input.Submitted) -> None:
        name = event.value.strip()
        if name:
            self.dismiss(name)
