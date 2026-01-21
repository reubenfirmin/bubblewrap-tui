"""Sandbox configuration widgets: DevModeCard, OptionCard."""

from typing import Callable

from textual import on
from textual.app import ComposeResult
from textual.containers import Container
from textual.widgets import Button, Checkbox, Static

from model.ui_field import UIField
from ui.ids import css
import ui.ids as ids


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
