"""Directories tab composition."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Callable

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import Button, Input, Label

from ui.widgets import BoundDirItem, FilteredDirectoryTree

if TYPE_CHECKING:
    from model import BoundDirectory


def compose_directories_tab(
    bound_dirs: list[BoundDirectory],
    on_update: Callable[[], None],
    on_remove: Callable[[BoundDirItem], None],
) -> ComposeResult:
    """Compose the directories tab content.

    Args:
        bound_dirs: List of bound directory configurations
        on_update: Callback when a directory is updated
        on_remove: Callback when a directory is removed

    Yields:
        Textual widgets for the directories tab
    """
    dir_items = [BoundDirItem(bd, on_update, on_remove) for bd in bound_dirs]

    with Horizontal(id="dirs-tab-content"):
        with Vertical(id="dir-browser-container"):
            yield Label("Browser")
            with Horizontal(id="dir-nav-buttons"):
                yield Button("..", id="parent-dir-btn")
                yield Button("Add Selected (a)", id="add-dir-btn", variant="primary")
            yield FilteredDirectoryTree(Path.cwd(), id="dir-tree")
            with Horizontal(id="path-input-row"):
                yield Input(placeholder="/path/to/add", id="path-input")
                yield Button("+", id="add-path-btn", variant="success")
        with Vertical(id="bound-dirs-container"):
            yield Label("Bound Directories (click ro/rw to toggle)")
            yield VerticalScroll(*dir_items, id="bound-dirs-list")
