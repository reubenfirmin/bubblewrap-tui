"""Directory event handlers."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

from textual import on
from textual.containers import VerticalScroll
from textual.css.query import NoMatches
from textual.widgets import Button, Input

if TYPE_CHECKING:
    from model import BoundDirectory


class DirectoryEventsMixin:
    """Mixin for directory-related event handlers."""

    # Expected from App class
    config: Any
    query_one: Callable
    _update_preview: Callable
    _set_status: Callable
    _remove_bound_dir: Callable

    @on(Button.Pressed, "#add-dir-btn")
    def on_add_dir_pressed(self, event: Button.Pressed) -> None:
        """Add the selected directory."""
        self.action_add_directory()

    @on(Button.Pressed, "#parent-dir-btn")
    def on_parent_dir_pressed(self, event: Button.Pressed) -> None:
        """Navigate to parent directory."""
        from ui import FilteredDirectoryTree

        try:
            tree = self.query_one("#dir-tree", FilteredDirectoryTree)
            current = tree.path
            parent = current.parent
            if parent != current:
                tree.path = parent
        except NoMatches:
            pass

    @on(Button.Pressed, "#add-path-btn")
    def on_add_path_pressed(self, event: Button.Pressed) -> None:
        """Add a path from the input field."""
        self._add_path_from_input()

    @on(Input.Submitted, "#path-input")
    def on_path_input_submitted(self, event: Input.Submitted) -> None:
        """Handle Enter in path input."""
        self._add_path_from_input()

    def _add_path_from_input(self) -> None:
        """Add a path from the input field."""
        from model import BoundDirectory
        from ui import BoundDirItem

        try:
            path_input = self.query_one("#path-input", Input)
            path_str = path_input.value.strip()
            if not path_str:
                return
            path = Path(path_str).expanduser().resolve()
            if not path.exists():
                self._set_status(f"Path does not exist: {path}")
                return
            if not path.is_dir():
                self._set_status(f"Not a directory: {path}")
                return
            # Check if already added
            for bd in self.config.bound_dirs:
                if bd.path == path:
                    self._set_status(f"Already added: {path}")
                    return
            bound_dir = BoundDirectory(path=path, readonly=True)
            self.config.bound_dirs.append(bound_dir)
            dirs_list = self.query_one("#bound-dirs-list", VerticalScroll)
            dirs_list.mount(BoundDirItem(bound_dir, self._update_preview, self._remove_bound_dir))
            path_input.value = ""
            self._update_preview()
            self._set_status(f"Added: {path}")
        except NoMatches:
            pass

    def action_add_directory(self) -> None:
        """Add the currently selected directory to the bound list."""
        from model import BoundDirectory
        from ui import BoundDirItem, FilteredDirectoryTree

        try:
            tree = self.query_one("#dir-tree", FilteredDirectoryTree)
            if tree.cursor_node and tree.cursor_node.data:
                path = (
                    tree.cursor_node.data.path
                    if hasattr(tree.cursor_node.data, "path")
                    else tree.cursor_node.data
                )
                if isinstance(path, Path) and path.is_dir():
                    # Check if already added
                    for bd in self.config.bound_dirs:
                        if bd.path == path:
                            self._set_status(f"Already added: {path}")
                            return

                    bound_dir = BoundDirectory(path=path, readonly=True)
                    self.config.bound_dirs.append(bound_dir)

                    dirs_list = self.query_one("#bound-dirs-list", VerticalScroll)
                    dirs_list.mount(
                        BoundDirItem(bound_dir, self._update_preview, self._remove_bound_dir)
                    )

                    self._update_preview()
                    self._set_status(f"Added: {path}")
        except NoMatches:
            pass
