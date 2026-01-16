"""Execute/cancel event handlers."""

from __future__ import annotations

from typing import Callable

from textual import on
from textual.widgets import Button


class ExecuteEventsMixin:
    """Mixin for execute/cancel event handlers."""

    _execute_command: bool
    exit: Callable

    @on(Button.Pressed, "#execute-btn")
    def on_execute_pressed(self, event: Button.Pressed) -> None:
        """Execute the command."""
        self.action_execute()

    @on(Button.Pressed, "#cancel-btn")
    def on_cancel_pressed(self, event: Button.Pressed) -> None:
        """Cancel and exit."""
        self.action_cancel()

    def action_execute(self) -> None:
        """Execute the configured command."""
        self._execute_command = True
        self.exit()

    def action_cancel(self) -> None:
        """Cancel and exit without executing."""
        self._execute_command = False
        self.exit()
