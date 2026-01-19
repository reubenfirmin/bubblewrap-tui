"""UI helper functions for bui."""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING, Callable

from textual.css.query import NoMatches
from textual.widgets import Checkbox

if TYPE_CHECKING:
    from typing import Any

    from textual.app import App

log = logging.getLogger(__name__)


def reflow_env_columns(
    app: App,
    env_config: Any,  # GroupProxy (environment)
    env_var_item_class: type,
    on_toggle: Callable[[str, bool], None],
) -> None:
    """Reflow environment variable items across columns.

    Args:
        app: The Textual app instance
        env_config: Environment configuration
        env_var_item_class: The EnvVarItem widget class
        on_toggle: Callback for toggling env vars
    """
    # Remove all existing items
    for item in app.query(env_var_item_class):
        item.remove()

    # Build list based on clear_env state
    if env_config.clear_env:
        # Only show custom vars when system env is cleared
        all_vars = [(n, v) for n, v in env_config.custom_env_vars.items()]
    else:
        # Show custom vars first, then sorted system vars
        all_vars = [(n, v) for n, v in env_config.custom_env_vars.items()]
        all_vars += sorted(os.environ.items())

    # Get column containers
    columns = list(app.query(".env-column"))
    if not columns or not all_vars:
        return

    # Distribute across columns
    third = max(1, len(all_vars) // 3)
    col_items = [all_vars[:third], all_vars[third : third * 2], all_vars[third * 2 :]]

    for col_idx, col in enumerate(columns):
        if col_idx < len(col_items):
            for name, value in col_items[col_idx]:
                is_kept = name in env_config.keep_env_vars
                item = env_var_item_class(name, value, on_toggle)
                col.mount(item)
                # Set checkbox state after mount
                try:
                    checkbox = item.query_one(".env-keep-toggle", Checkbox)
                    checkbox.value = is_kept
                except NoMatches:
                    log.debug("Checkbox not found in env var item")
