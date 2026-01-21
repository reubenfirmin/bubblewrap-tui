"""Directory event handlers."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

from textual import on
from textual.containers import VerticalScroll
from textual.css.query import NoMatches
from textual.widgets import Button, Input

from ui.ids import css
import ui.ids as ids

if TYPE_CHECKING:
    from model import BoundDirectory

log = logging.getLogger(__name__)


class DirectoryEventsMixin:
    """Mixin for directory-related event handlers."""

    # Expected from App class
    config: Any
    query_one: Callable
    _update_preview: Callable
    _set_status: Callable
    _remove_bound_dir: Callable

    def _is_path_already_bound(self, path: Path) -> bool:
        """Check if a path is already in bound directories."""
        resolved_path = path.resolve()
        return any(bd.path.resolve() == resolved_path for bd in self.config.bound_dirs)

    def _check_vfs_conflict(self, path: Path) -> str | None:
        """Check if path conflicts with VFS options. Returns warning message or None."""
        resolved = path.resolve()
        if resolved == Path("/proc") and self.config.vfs.mount_proc:
            return "/proc is already mounted via Virtual Filesystems"
        if resolved == Path("/tmp") and self.config.vfs.mount_tmp:
            return "/tmp is already mounted via Virtual Filesystems"
        return None

    @on(Button.Pressed, css(ids.ADD_DIR_BTN))
    def on_add_dir_pressed(self, event: Button.Pressed) -> None:
        """Add the selected directory."""
        self.action_add_directory()

    @on(Button.Pressed, css(ids.PARENT_DIR_BTN))
    def on_parent_dir_pressed(self, event: Button.Pressed) -> None:
        """Navigate to parent directory."""
        from ui import FilteredDirectoryTree

        try:
            tree = self.query_one(css(ids.DIR_TREE), FilteredDirectoryTree)
            current = tree.path
            parent = current.parent
            if parent != current:
                tree.path = parent
        except NoMatches:
            log.debug("Directory tree not found for parent navigation")

    @on(Button.Pressed, css(ids.ADD_PATH_BTN))
    def on_add_path_pressed(self, event: Button.Pressed) -> None:
        """Add a path from the input field."""
        self._add_path_from_input()

    @on(Input.Submitted, css(ids.PATH_INPUT))
    def on_path_input_submitted(self, event: Input.Submitted) -> None:
        """Handle Enter in path input."""
        self._add_path_from_input()

    def _add_path_from_input(self) -> None:
        """Add a path from the input field."""
        from model import BoundDirectory
        from ui import BoundDirItem

        try:
            path_input = self.query_one(css(ids.PATH_INPUT), Input)
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
            if self._is_path_already_bound(path):
                self._set_status(f"Already added: {path}")
                return
            conflict = self._check_vfs_conflict(path)
            if conflict:
                self._set_status(conflict)
                return
            bound_dir = BoundDirectory(path=path, readonly=True)
            self.config.bound_dirs.append(bound_dir)
            dirs_list = self.query_one(css(ids.BOUND_DIRS_LIST), VerticalScroll)
            dirs_list.mount(BoundDirItem(bound_dir, self._update_preview, self._remove_bound_dir))
            path_input.value = ""
            self._update_preview()
            self._set_status(f"Added: {path}")
        except NoMatches:
            log.debug("Path input or dirs list not found")

    def action_add_directory(self) -> None:
        """Add the currently selected directory to the bound list."""
        from model import BoundDirectory
        from ui import BoundDirItem, FilteredDirectoryTree

        try:
            tree = self.query_one(css(ids.DIR_TREE), FilteredDirectoryTree)
            if tree.cursor_node and tree.cursor_node.data:
                path = (
                    tree.cursor_node.data.path
                    if hasattr(tree.cursor_node.data, "path")
                    else tree.cursor_node.data
                )
                if isinstance(path, Path) and path.is_dir():
                    if self._is_path_already_bound(path):
                        self._set_status(f"Already added: {path}")
                        return
                    conflict = self._check_vfs_conflict(path)
                    if conflict:
                        self._set_status(conflict)
                        return

                    bound_dir = BoundDirectory(path=path, readonly=True)
                    self.config.bound_dirs.append(bound_dir)

                    dirs_list = self.query_one(css(ids.BOUND_DIRS_LIST), VerticalScroll)
                    dirs_list.mount(
                        BoundDirItem(bound_dir, self._update_preview, self._remove_bound_dir)
                    )

                    self._update_preview()
                    self._set_status(f"Added: {path}")
        except NoMatches:
            log.debug("Directory tree or dirs list not found")
