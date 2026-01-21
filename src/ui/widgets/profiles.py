"""Profile management widget: ProfileItem."""

from pathlib import Path
from typing import Callable

from textual import on
from textual.app import ComposeResult
from textual.containers import Container, Horizontal
from textual.widgets import Button


class ProfileItem(Container):
    """A clickable profile entry in the profiles list."""

    def __init__(self, profile_path: Path, on_load: Callable, on_delete: Callable) -> None:
        super().__init__()
        self.profile_path = profile_path
        self._on_load = on_load
        self._on_delete = on_delete

    def compose(self) -> ComposeResult:
        with Horizontal(classes="profile-row"):
            yield Button(self.profile_path.stem, classes="profile-name-btn", variant="primary")
            yield Button("x", classes="profile-delete-btn", variant="error")

    @on(Button.Pressed, ".profile-name-btn")
    def on_load_pressed(self, event: Button.Pressed) -> None:
        event.stop()
        self._on_load(self.profile_path)

    @on(Button.Pressed, ".profile-delete-btn")
    def on_delete_pressed(self, event: Button.Pressed) -> None:
        event.stop()
        self._on_delete(self)
