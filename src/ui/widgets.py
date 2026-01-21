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


class OverlayItem(Container):
    """A row representing an overlay configuration.

    Modes:
        tmpfs: Empty writable directory (no source needed)
        overlay: Writable layer on existing dir, changes in RAM
        persistent: Writable layer on existing dir, changes saved to disk
    """

    # Mode cycle order and display properties
    MODES = ["tmpfs", "overlay", "persistent"]
    MODE_LABELS = {"tmpfs": "tmpfs", "overlay": "overlay", "persistent": "persist"}
    MODE_VARIANTS = {"tmpfs": "default", "overlay": "primary", "persistent": "warning"}

    def __init__(self, overlay: OverlayConfig, on_update: Callable, on_remove: Callable) -> None:
        super().__init__()
        self.overlay = overlay
        self._on_update = on_update
        self._on_remove = on_remove

    def compose(self) -> ComposeResult:
        mode = self.overlay.mode
        with Horizontal(classes="overlay-row"):
            yield Button(self.MODE_LABELS.get(mode, mode),
                        classes="overlay-mode-btn",
                        variant=self.MODE_VARIANTS.get(mode, "default"))
            # Source: disabled for tmpfs (not needed), enabled for overlay/persistent
            yield Input(value=self.overlay.source,
                       placeholder="n/a" if mode == "tmpfs" else "Source dir",
                       classes="overlay-src-input",
                       disabled=(mode == "tmpfs"))
            yield Static("→", classes="overlay-arrow")
            yield Input(value=self.overlay.dest, placeholder="Mount point", classes="overlay-dest-input")
            # Write dir: only for persistent mode
            yield Input(
                value=self.overlay.write_dir if mode == "persistent" else "",
                placeholder="Write dir" if mode == "persistent" else "n/a",
                classes="overlay-write-input",
                disabled=(mode != "persistent")
            )
            yield Button("x", classes="overlay-remove-btn", variant="error")

    @on(Button.Pressed, ".overlay-mode-btn")
    def on_mode_toggle(self, event: Button.Pressed) -> None:
        event.stop()
        # Cycle to next mode
        current_idx = self.MODES.index(self.overlay.mode) if self.overlay.mode in self.MODES else 0
        next_idx = (current_idx + 1) % len(self.MODES)
        self.overlay.mode = self.MODES[next_idx]
        mode = self.overlay.mode

        # Update button
        btn = event.button
        btn.label = self.MODE_LABELS.get(mode, mode)
        btn.variant = self.MODE_VARIANTS.get(mode, "default")

        # Update source input (disabled for tmpfs)
        src_input = self.query_one(".overlay-src-input", Input)
        src_input.disabled = (mode == "tmpfs")
        src_input.placeholder = "n/a" if mode == "tmpfs" else "Source dir"
        if mode == "tmpfs":
            src_input.value = ""
            self.overlay.source = ""

        # Update write dir input (only for persistent)
        write_input = self.query_one(".overlay-write-input", Input)
        write_input.disabled = (mode != "persistent")
        write_input.placeholder = "Write dir" if mode == "persistent" else "n/a"
        if mode != "persistent":
            write_input.value = ""
            self.overlay.write_dir = ""

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
        # Give explanation an ID derived from checkbox ID for dynamic updates
        explanation_id = f"{self.field.checkbox_id}-explanation"
        yield Static(self._explanation, classes="option-explanation", id=explanation_id)


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


# =============================================================================
# Network Filtering Widgets
# =============================================================================


class PastaStatus(Container):
    """Shows pasta installation status and install command if missing."""

    def __init__(self) -> None:
        super().__init__()
        self._installed = False
        self._message = ""

    def compose(self) -> ComposeResult:
        from net import get_pasta_status

        self._installed, self._message = get_pasta_status()
        if self._installed:
            yield Static("pasta: [green]installed[/green]", id="pasta-status")
        else:
            yield Static(
                f"pasta: [red]not found[/red] - {self._message}",
                id="pasta-status",
            )

    @property
    def is_installed(self) -> bool:
        return self._installed


class FilterModeRadio(Container):
    """Radio button group for Off/Whitelist/Blacklist filter mode."""

    def __init__(
        self,
        mode: str = "off",
        on_change: Callable | None = None,
        radio_id: str = "",
    ) -> None:
        super().__init__()
        self._mode = mode
        self._on_change = on_change
        self._radio_id = radio_id

    def compose(self) -> ComposeResult:
        from textual.widgets import RadioButton, RadioSet

        with RadioSet(id=self._radio_id):
            yield RadioButton("Off", value=(self._mode == "off"))
            yield RadioButton("Whitelist", value=(self._mode == "whitelist"))
            yield RadioButton("Blacklist", value=(self._mode == "blacklist"))

    def on_radio_set_changed(self, event) -> None:
        """Handle radio selection change."""
        modes = ["off", "whitelist", "blacklist"]
        if event.pressed:
            self._mode = modes[event.radio_set.pressed_index]
            if self._on_change:
                self._on_change(self._mode)

    @property
    def mode(self) -> str:
        return self._mode

    def set_mode(self, mode: str) -> None:
        """Set the mode programmatically."""
        from textual.widgets import RadioSet

        self._mode = mode
        modes = ["off", "whitelist", "blacklist"]
        if mode in modes:
            idx = modes.index(mode)
            try:
                radio_set = self.query_one(RadioSet)
                radio_set.pressed_index = idx
            except Exception:
                pass


class FilterListItem(Container):
    """A single item in a filter list (hostname or CIDR)."""

    def __init__(self, value: str, on_remove: Callable) -> None:
        super().__init__()
        self.value = value
        self._on_remove = on_remove

    def compose(self) -> ComposeResult:
        yield Label(self.value, classes="filter-item-label")
        yield Button("x", classes="filter-remove-btn", variant="error")

    @on(Button.Pressed, ".filter-remove-btn")
    def on_remove_pressed(self, event: Button.Pressed) -> None:
        event.stop()
        self._on_remove(self)


class FilterList(Container):
    """A list of filter items with add/remove functionality."""

    def __init__(
        self,
        items: list[str],
        on_add: Callable,
        on_remove: Callable,
        placeholder: str = "Enter value...",
        list_id: str = "",
        input_id: str = "",
        add_btn_id: str = "",
        validate_fn: Callable[[str], bool] | None = None,
    ) -> None:
        super().__init__()
        self._items = items
        self._on_add = on_add
        self._on_remove = on_remove
        self._placeholder = placeholder
        self._list_id = list_id
        self._input_id = input_id
        self._add_btn_id = add_btn_id
        self._validate_fn = validate_fn

    def compose(self) -> ComposeResult:
        with VerticalScroll(id=self._list_id, classes="filter-list-scroll"):
            for item in self._items:
                yield FilterListItem(item, self._handle_remove)
        with Horizontal(classes="filter-add-row"):
            yield Input(placeholder=self._placeholder, id=self._input_id)
            yield Button("+", id=self._add_btn_id, variant="success")

    def _handle_remove(self, item: FilterListItem) -> None:
        """Handle item removal."""
        if item.value in self._items:
            self._items.remove(item.value)
        item.remove()
        self._on_remove(item.value)

    @on(Button.Pressed)
    def on_add_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == self._add_btn_id:
            event.stop()
            self._add_item()

    @on(Input.Submitted)
    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == self._input_id:
            event.stop()
            self._add_item()

    def _add_item(self) -> None:
        """Add item from input field."""
        try:
            input_widget = self.query_one(f"#{self._input_id}", Input)
            value = input_widget.value.strip()
            if not value:
                return

            # Validate if function provided
            if self._validate_fn and not self._validate_fn(value):
                return

            # Avoid duplicates
            if value in self._items:
                input_widget.value = ""
                return

            self._items.append(value)
            input_widget.value = ""

            # Mount new item
            list_scroll = self.query_one(f"#{self._list_id}", VerticalScroll)
            list_scroll.mount(FilterListItem(value, self._handle_remove))

            self._on_add(value)
        except Exception:
            pass

    def refresh_items(self, items: list[str]) -> None:
        """Refresh the list with new items."""
        self._items = items
        try:
            list_scroll = self.query_one(f"#{self._list_id}", VerticalScroll)
            # Remove existing items
            for item in list(list_scroll.query(FilterListItem)):
                item.remove()
            # Add new items
            for value in items:
                list_scroll.mount(FilterListItem(value, self._handle_remove))
        except Exception:
            pass


class PortListItem(Container):
    """A single port item in the port list."""

    def __init__(self, port: int, on_remove: Callable) -> None:
        super().__init__()
        self.port = port
        self._on_remove = on_remove

    def compose(self) -> ComposeResult:
        yield Label(str(self.port), classes="filter-item-label")
        yield Button("x", classes="filter-remove-btn", variant="error")

    @on(Button.Pressed, ".filter-remove-btn")
    def on_remove_pressed(self, event: Button.Pressed) -> None:
        event.stop()
        self._on_remove(self)


class PortList(Container):
    """A list of port numbers with add/remove functionality."""

    def __init__(
        self,
        ports: list[int],
        on_add: Callable,
        on_remove: Callable,
        list_id: str = "",
        input_id: str = "",
        add_btn_id: str = "",
    ) -> None:
        super().__init__()
        self._ports = ports
        self._on_add = on_add
        self._on_remove = on_remove
        self._list_id = list_id
        self._input_id = input_id
        self._add_btn_id = add_btn_id

    def compose(self) -> ComposeResult:
        with VerticalScroll(id=self._list_id, classes="filter-list-scroll"):
            for port in self._ports:
                yield PortListItem(port, self._handle_remove)
        with Horizontal(classes="filter-add-row"):
            yield Input(placeholder="Port (1-65535)", id=self._input_id)
            yield Button("+", id=self._add_btn_id, variant="success")

    def _handle_remove(self, item: PortListItem) -> None:
        """Handle port removal."""
        if item.port in self._ports:
            self._ports.remove(item.port)
        item.remove()
        self._on_remove(item.port)

    @on(Button.Pressed)
    def on_add_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == self._add_btn_id:
            event.stop()
            self._add_port()

    @on(Input.Submitted)
    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == self._input_id:
            event.stop()
            self._add_port()

    def _add_port(self) -> None:
        """Add port from input field."""
        from net import validate_port

        try:
            input_widget = self.query_one(f"#{self._input_id}", Input)
            value = input_widget.value.strip()
            if not value:
                return

            # Validate port
            if not validate_port(value):
                return

            port = int(value)

            # Avoid duplicates
            if port in self._ports:
                input_widget.value = ""
                return

            self._ports.append(port)
            input_widget.value = ""

            # Mount new item
            list_scroll = self.query_one(f"#{self._list_id}", VerticalScroll)
            list_scroll.mount(PortListItem(port, self._handle_remove))

            self._on_add(port)
        except Exception:
            pass

    def refresh_ports(self, ports: list[int]) -> None:
        """Refresh the list with new ports."""
        self._ports = ports
        try:
            list_scroll = self.query_one(f"#{self._list_id}", VerticalScroll)
            # Remove existing items
            for item in list(list_scroll.query(PortListItem)):
                item.remove()
            # Add new items
            for port in ports:
                list_scroll.mount(PortListItem(port, self._handle_remove))
        except Exception:
            pass
