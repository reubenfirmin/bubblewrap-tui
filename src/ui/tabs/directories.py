"""Directories tab composition."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Callable

from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.widgets import Button, Input, Label, Static

from model import groups
from model.groups import QUICK_SHORTCUTS
from ui.widgets import BoundDirItem, FilteredDirectoryTree, OptionCard

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

    yield Static(
        "Directories listed here will be accessible inside the sandbox.",
        id="dirs-hint",
    )
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
            # Quick shortcuts card - scrollable, shrinks on small screens
            with VerticalScroll(id="quick-shortcuts-section"):
                yield Label("Quick Shortcuts", classes="section-label")
                for field in QUICK_SHORTCUTS:
                    # Use field's default, except disable if path doesn't exist
                    path = getattr(field, "shortcut_path", None)
                    if path and not path.exists():
                        default = False
                    else:
                        default = field.default
                    yield OptionCard(field, default=default)
        with Vertical(id="bound-dirs-container"):
            yield Label("Bound Directories (click ro/rw to toggle)")
            yield VerticalScroll(*dir_items, id="bound-dirs-list")
