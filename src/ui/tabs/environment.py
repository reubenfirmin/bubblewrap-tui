"""Environment tab composition."""

from __future__ import annotations

import os
from typing import Callable

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import Button, Static

from ui.widgets import EnvVarItem


def compose_environment_tab(on_toggle: Callable[[str, bool], None]) -> ComposeResult:
    """Compose the environment tab content.

    Args:
        on_toggle: Callback when an env var checkbox is toggled

    Yields:
        Textual widgets for the environment tab
    """
    with Vertical(id="env-tab-content"):
        with Horizontal(id="env-buttons-row"):
            yield Button("+ Add Variables", id="add-env-btn", variant="success")
            yield Button("Clear System Env", id="toggle-clear-btn", variant="error")
        with VerticalScroll(id="env-grid-scroll"):
            yield Static(
                "Sandbox will inherit all checked environment variables. "
                "Use Clear All to start with an empty environment.",
                id="env-hint",
            )
            with Horizontal(id="env-grid"):
                # Split env vars into 3 columns
                env_items = sorted(os.environ.items())
                third = max(1, len(env_items) // 3)
                columns = [
                    env_items[:third],
                    env_items[third : third * 2],
                    env_items[third * 2 :],
                ]
                for col_items in columns:
                    with Vertical(classes="env-column"):
                        for name, value in col_items:
                            yield EnvVarItem(name, value, on_toggle)
