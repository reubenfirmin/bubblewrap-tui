"""Directory-related widgets: FilteredDirectoryTree, BoundDirItem."""

from pathlib import Path
from typing import Callable

from textual import on
from textual.app import ComposeResult
from textual.containers import Container
from textual.widgets import Button, DirectoryTree, Label

from model import BoundDirectory


class FilteredDirectoryTree(DirectoryTree):
    """A directory tree that only shows directories."""

    def filter_paths(self, paths: list[Path]) -> list[Path]:
        return [p for p in paths if p.is_dir()]


def is_user_owned(path: Path) -> bool:
    """Check if a path is owned by the current user."""
    import os
    try:
        return path.stat().st_uid == os.getuid()
    except (OSError, FileNotFoundError):
        return False


class BoundDirItem(Container):
    """A row representing a bound directory."""

    def __init__(
        self,
        bound_dir: BoundDirectory,
        on_update: Callable,
        on_remove: Callable,
    ) -> None:
        super().__init__()
        self.bound_dir = bound_dir
        self._on_update = on_update
        self._on_remove = on_remove
        self._user_owned = is_user_owned(bound_dir.path)

    def compose(self) -> ComposeResult:
        mode = "ro" if self.bound_dir.readonly else "rw"
        variant = "default" if self.bound_dir.readonly else "warning"
        # Disable RW toggle if not user-owned
        yield Button(mode, classes="mode-btn", variant=variant, disabled=not self._user_owned)
        yield Label(str(self.bound_dir.path), classes="bound-path")
        yield Button("x", classes="remove-btn", variant="error")

    @on(Button.Pressed, ".mode-btn")
    def on_mode_toggle(self, event: Button.Pressed) -> None:
        event.stop()
        if not self._user_owned:
            return
        self.bound_dir.readonly = not self.bound_dir.readonly
        btn = self.query_one(".mode-btn", Button)
        btn.label = "ro" if self.bound_dir.readonly else "rw"
        btn.variant = "default" if self.bound_dir.readonly else "warning"
        self._on_update()

    @on(Button.Pressed, ".remove-btn")
    def on_remove_pressed(self, event: Button.Pressed) -> None:
        event.stop()
        self._on_remove(self)
