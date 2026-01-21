"""Environment variable widgets: EnvVarItem, EnvVarRow, AddEnvDialog."""

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

from ui.ids import css
import ui.ids as ids


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
