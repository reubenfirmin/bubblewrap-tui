"""Environment event handlers."""

from __future__ import annotations

import os
from typing import Any, Callable

from textual import on
from textual.css.query import NoMatches
from textual.widgets import Button, Checkbox

from ui.ids import css
import ui.ids as ids


class EnvironmentEventsMixin:
    """Mixin for environment-related event handlers."""

    config: Any
    query: Callable
    query_one: Callable
    push_screen: Callable
    _update_preview: Callable
    _set_status: Callable
    _reflow_env_columns: Callable
    _sync_env_button_state: Callable

    @on(Button.Pressed, css(ids.TOGGLE_CLEAR_BTN))
    def on_toggle_clear_pressed(self, event: Button.Pressed) -> None:
        """Toggle between clear and restore environment."""
        from ui import EnvVarItem

        try:
            if not self.config.environment.clear_env:
                # Clear environment
                self.config.environment.clear_env = True
                self.config.environment.keep_env_vars = set(
                    self.config.environment.custom_env_vars.keys()
                )
                self._sync_env_button_state()
                self._update_preview()
                self._set_status("Sandbox environment cleared")
            else:
                # Restore environment
                self.config.environment.clear_env = False
                self.config.environment.keep_env_vars = set(os.environ.keys()) | set(
                    self.config.environment.custom_env_vars.keys()
                )
                self.config.environment.unset_env_vars.clear()
                self._sync_env_button_state()
                # Check all env var checkboxes
                for item in self.query(EnvVarItem):
                    checkbox = item.query_one(".env-keep-toggle", Checkbox)
                    checkbox.value = True
                self._update_preview()
                self._set_status("System environment restored")
        except NoMatches:
            pass

    @on(Button.Pressed, css(ids.ADD_ENV_BTN))
    def on_add_env_pressed(self, event: Button.Pressed) -> None:
        """Open dialog to add environment variables."""
        from ui import AddEnvDialog

        self.push_screen(AddEnvDialog(), self._handle_add_env_result)

    def _handle_add_env_result(self, pairs: list[tuple[str, str]]) -> None:
        """Handle result from add env dialog."""
        if not pairs:
            return
        for name, value in pairs:
            self.config.environment.custom_env_vars[name] = value
            self.config.environment.keep_env_vars.add(name)
        # Only show env grid if not in cleared state, or if we have custom vars to show
        if self.config.environment.custom_env_vars:
            try:
                self.query_one(css(ids.ENV_GRID_SCROLL)).remove_class("hidden")
            except NoMatches:
                pass
        self._reflow_env_columns()
        self._update_preview()
        self._set_status(f"Added {len(pairs)} variable(s)")
