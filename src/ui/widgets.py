"""Custom Textual widgets for bui."""

from pathlib import Path
from typing import Callable

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import (
    Button,
    Checkbox,
    DirectoryTree,
    Input,
    Label,
    Static,
    TabbedContent,
    TabPane,
)

from model import BoundDirectory, OverlayConfig
from model.ui_field import UIField
from ui.ids import css
import ui.ids as ids


class FilteredDirectoryTree(DirectoryTree):
    """A directory tree that only shows directories."""

    def filter_paths(self, paths: list[Path]) -> list[Path]:
        return [p for p in paths if p.is_dir()]


class BoundDirItem(Container):
    """A row representing a bound directory."""

    def __init__(self, bound_dir: BoundDirectory, on_update: Callable, on_remove: Callable) -> None:
        super().__init__()
        self.bound_dir = bound_dir
        self._on_update = on_update
        self._on_remove = on_remove

    def compose(self) -> ComposeResult:
        mode = "ro" if self.bound_dir.readonly else "rw"
        variant = "default" if self.bound_dir.readonly else "warning"
        yield Button(mode, classes="mode-btn", variant=variant)
        yield Label(str(self.bound_dir.path), classes="bound-path")
        yield Button("x", classes="remove-btn", variant="error")

    @on(Button.Pressed, ".mode-btn")
    def on_mode_toggle(self, event: Button.Pressed) -> None:
        event.stop()
        self.bound_dir.readonly = not self.bound_dir.readonly
        btn = self.query_one(".mode-btn", Button)
        btn.label = "ro" if self.bound_dir.readonly else "rw"
        btn.variant = "default" if self.bound_dir.readonly else "warning"
        self._on_update()

    @on(Button.Pressed, ".remove-btn")
    def on_remove_pressed(self, event: Button.Pressed) -> None:
        event.stop()
        self._on_remove(self)


class OverlayItem(Container):
    """A row representing an overlay configuration."""

    def __init__(self, overlay: OverlayConfig, on_update: Callable, on_remove: Callable) -> None:
        super().__init__()
        self.overlay = overlay
        self._on_update = on_update
        self._on_remove = on_remove

    def compose(self) -> ComposeResult:
        with Horizontal(classes="overlay-row"):
            yield Button("tmpfs" if self.overlay.mode == "tmpfs" else "persist",
                        classes="overlay-mode-btn",
                        variant="default" if self.overlay.mode == "tmpfs" else "warning")
            yield Input(value=self.overlay.source, placeholder="Source dir", classes="overlay-src-input")
            yield Static("→", classes="overlay-arrow")
            yield Input(value=self.overlay.dest, placeholder="Mount point", classes="overlay-dest-input")
            is_tmpfs = self.overlay.mode == "tmpfs"
            yield Input(
                value="" if is_tmpfs else self.overlay.write_dir,
                placeholder="n/a (tmpfs)" if is_tmpfs else "Write dir",
                classes="overlay-write-input",
                disabled=is_tmpfs
            )
            yield Button("x", classes="overlay-remove-btn", variant="error")

    @on(Button.Pressed, ".overlay-mode-btn")
    def on_mode_toggle(self, event: Button.Pressed) -> None:
        event.stop()
        self.overlay.mode = "persistent" if self.overlay.mode == "tmpfs" else "tmpfs"
        btn = event.button
        btn.label = "tmpfs" if self.overlay.mode == "tmpfs" else "persist"
        btn.variant = "default" if self.overlay.mode == "tmpfs" else "warning"
        # Enable/disable write dir input
        write_input = self.query_one(".overlay-write-input", Input)
        is_tmpfs = self.overlay.mode == "tmpfs"
        write_input.disabled = is_tmpfs
        write_input.placeholder = "n/a (tmpfs)" if is_tmpfs else "Write dir"
        if is_tmpfs:
            write_input.value = ""
        self._on_update()

    @on(Input.Changed, ".overlay-src-input")
    def on_src_changed(self, event: Input.Changed) -> None:
        old_source = self.overlay.source
        self.overlay.source = event.value
        # Auto-sync dest if it matches source (user hasn't customized it)
        dest_input = self.query_one(".overlay-dest-input", Input)
        if not dest_input.value or dest_input.value == old_source:
            dest_input.value = event.value
            self.overlay.dest = event.value
        self._on_update()

    @on(Input.Changed, ".overlay-dest-input")
    def on_dest_changed(self, event: Input.Changed) -> None:
        self.overlay.dest = event.value
        self._on_update()

    @on(Input.Changed, ".overlay-write-input")
    def on_write_changed(self, event: Input.Changed) -> None:
        self.overlay.write_dir = event.value
        self._on_update()

    @on(Button.Pressed, ".overlay-remove-btn")
    def on_remove_pressed(self, event: Button.Pressed) -> None:
        event.stop()
        self._on_remove(self)


class EnvVarItem(Container):
    """A card for an environment variable."""

    def __init__(self, name: str, value: str, on_toggle: Callable) -> None:
        super().__init__()
        self.var_name = name
        self.var_value = value
        self._on_toggle = on_toggle

    def compose(self) -> ComposeResult:
        yield Checkbox(self.var_name, value=True, classes="env-keep-toggle")
        display_val = self.var_value[:30] + "..." if len(self.var_value) > 30 else self.var_value
        yield Static(display_val, classes="env-value")

    @on(Checkbox.Changed)
    def on_keep_toggle(self, event: Checkbox.Changed) -> None:
        self._on_toggle(self.var_name, event.value)


class EnvVarRow(Container):
    """A row for entering a name/value pair."""

    def compose(self) -> ComposeResult:
        yield Input(placeholder="NAME", classes="env-name-input")
        yield Input(placeholder="value", classes="env-value-input")
        yield Button("x", classes="remove-row-btn", variant="error")


class AddEnvDialog(ModalScreen[list[tuple[str, str]]]):
    """Modal dialog for adding environment variables."""

    CSS = """
    AddEnvDialog {
        align: center middle;
    }

    #add-env-dialog {
        width: 80;
        height: 50;
        background: $surface;
        border: solid $primary;
        padding: 1;
    }

    #add-env-dialog > Label {
        text-style: bold;
        margin-bottom: 1;
    }

    #env-dialog-tabs {
        height: 1fr;
    }

    #dialog-buttons {
        height: auto;
        dock: bottom;
        align: right middle;
        padding: 1 0;
    }

    #dialog-buttons Button {
        margin-left: 1;
    }

    #env-rows-container {
        height: 1fr;
        padding: 1 3 1 1;
    }

    EnvVarRow {
        layout: horizontal;
        height: auto;
        width: 100%;
        margin-bottom: 1;
    }

    EnvVarRow .env-name-input {
        width: 1fr;
    }

    EnvVarRow .env-value-input {
        width: 2fr;
    }

    EnvVarRow .remove-row-btn {
        width: 3;
        min-width: 3;
        height: 1;
        min-height: 1;
        padding: 0;
        margin: 0;
    }

    .hint-text {
        color: $text-muted;
        height: auto;
        margin: 1 0;
    }

    #dotenv-container {
        padding: 1;
        height: 1fr;
    }

    #dotenv-tree {
        height: 20;
        margin-bottom: 1;
    }

    #dotenv-preview {
        height: auto;
        padding: 1;
        color: $text-muted;
    }

    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
    ]

    def on_mount(self) -> None:
        """Add initial row when dialog mounts."""
        container = self.query_one(css(ids.ENV_ROWS_CONTAINER), VerticalScroll)
        container.mount(EnvVarRow())

    def compose(self) -> ComposeResult:
        with Container(id="add-env-dialog"):
            yield Label("Add Environment Variables")
            with TabbedContent(id="env-dialog-tabs"):
                with TabPane("Add Variables", id="add-vars-tab"):
                    yield Static("Enter = add row, Tab/Shift+Tab = navigate", classes="hint-text")
                    yield VerticalScroll(id="env-rows-container")
                with TabPane("Import .env", id="import-tab"):
                    with Vertical(id="dotenv-container"):
                        yield Button("..", id="dotenv-parent-btn")
                        yield DirectoryTree(Path.cwd(), id="dotenv-tree")
                        yield Static("Select a .env file above", id="dotenv-preview")
            with Horizontal(id="dialog-buttons"):
                yield Button("Cancel", id="cancel-btn", variant="default")
                yield Button("Add", id="add-btn", variant="success")

    def _get_env_pairs(self) -> list[tuple[str, str]]:
        """Get all non-empty name/value pairs from the rows."""
        pairs = []
        for row in self.query(EnvVarRow):
            name_input = row.query_one(".env-name-input", Input)
            value_input = row.query_one(".env-value-input", Input)
            name = name_input.value.strip()
            value = value_input.value.strip()
            # Only add if name is non-empty
            if name:
                pairs.append((name, value))
        return pairs

    @on(Input.Submitted)
    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle Enter key in input fields."""
        self._add_new_row()
        # Focus the new row's name input
        rows = list(self.query(EnvVarRow))
        if rows:
            rows[-1].query_one(".env-name-input", Input).focus()

    def _add_new_row(self) -> None:
        """Add a new env var row."""
        container = self.query_one(css(ids.ENV_ROWS_CONTAINER), VerticalScroll)
        container.mount(EnvVarRow())

    @on(Button.Pressed, ".remove-row-btn")
    def on_remove_row(self, event: Button.Pressed) -> None:
        event.stop()
        row = event.button.parent
        if row and len(self.query(EnvVarRow)) > 1:
            row.remove()

    @on(Button.Pressed, css(ids.DOTENV_PARENT_BTN))
    def on_dotenv_parent(self, event: Button.Pressed) -> None:
        tree = self.query_one(css(ids.DOTENV_TREE), DirectoryTree)
        current = tree.path
        parent = current.parent
        if parent != current:
            tree.path = parent

    @on(DirectoryTree.FileSelected, css(ids.DOTENV_TREE))
    def on_dotenv_selected(self, event: DirectoryTree.FileSelected) -> None:
        preview = self.query_one(css(ids.DOTENV_PREVIEW), Static)
        path = event.path

        try:
            lines = []
            with open(path) as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        lines.append(line)

            if lines:
                # Add rows for each env var
                container = self.query_one(css(ids.ENV_ROWS_CONTAINER), VerticalScroll)
                for line in lines:
                    name, _, value = line.partition("=")
                    name = name.strip()
                    value = value.strip().strip('"').strip("'")
                    row = EnvVarRow()
                    container.mount(row)
                    # Set values after mount
                    row.query_one(".env-name-input", Input).value = name
                    row.query_one(".env-value-input", Input).value = value

                preview.update(f"Loaded {len(lines)} variables from {path.name}. Switch to 'Add Variables' tab to review.")
            else:
                preview.update(f"No valid environment variables found in {path.name}.")
        except Exception as e:
            preview.update(f"Error reading file: {e}")

    @on(Button.Pressed, css(ids.ADD_BTN))
    def on_add(self, event: Button.Pressed) -> None:
        pairs = self._get_env_pairs()
        self.dismiss(pairs)

    @on(Button.Pressed, css(ids.CANCEL_BTN))
    def on_cancel(self, event: Button.Pressed) -> None:
        self.dismiss([])

    def action_cancel(self) -> None:
        self.dismiss([])


class DevModeCard(Container):
    """A card for selecting /dev mode: none, minimal, full."""

    DEV_MODES = {
        "none": ("No /dev", "No device access"),
        "minimal": ("/dev minimal", "null, zero, random, urandom, tty"),
        "full": ("/dev full", "Full host /dev access - use with caution"),
    }
    MODE_ORDER = ["none", "minimal", "full"]

    def __init__(self, on_change: Callable) -> None:
        super().__init__()
        self._on_change = on_change
        self._mode = "minimal"

    def compose(self) -> ComposeResult:
        label, desc = self.DEV_MODES[self._mode]
        yield Button(label, id="dev-mode-btn")
        yield Static(desc, id="dev-mode-desc", classes="option-explanation")

    def set_mode(self, mode: str) -> None:
        self._mode = mode
        label, desc = self.DEV_MODES[mode]
        self.query_one(css(ids.DEV_MODE_BTN), Button).label = label
        self.query_one(css(ids.DEV_MODE_DESC), Static).update(desc)

    @on(Button.Pressed, css(ids.DEV_MODE_BTN))
    def on_mode_pressed(self, event: Button.Pressed) -> None:
        event.stop()
        idx = self.MODE_ORDER.index(self._mode)
        self._mode = self.MODE_ORDER[(idx + 1) % len(self.MODE_ORDER)]
        label, desc = self.DEV_MODES[self._mode]
        self.query_one(css(ids.DEV_MODE_BTN), Button).label = label
        self.query_one(css(ids.DEV_MODE_DESC), Static).update(desc)
        self._on_change(self._mode)


class OptionCard(Container):
    """A checkbox with label on row 1, explanation on row 2."""

    def __init__(self, field: UIField, default: bool | None = None, explanation: str | None = None) -> None:
        """Create an OptionCard from a UIField.

        Args:
            field: The UIField descriptor containing metadata
            default: Override the field's default (e.g., for /lib64 existence check)
            explanation: Override the field's explanation (e.g., for display detection)
        """
        super().__init__()
        self.field = field
        self._default = default if default is not None else field.default
        self._explanation = explanation or field.explanation

    def compose(self) -> ComposeResult:
        yield Checkbox(self.field.label, value=self._default, id=self.field.checkbox_id)
        yield Static(self._explanation, classes="option-explanation")


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
