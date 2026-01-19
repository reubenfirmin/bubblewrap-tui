"""Summary tab composition."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Label, Static


def compose_summary_tab(version: str, command_preview: str, explanation: str) -> ComposeResult:
    """Compose the summary tab content.

    Args:
        version: Application version string
        command_preview: Formatted bwrap command preview
        explanation: Human-readable explanation of sandbox settings

    Yields:
        Textual widgets for the summary tab
    """
    with Vertical(id="summary-tab-content"):
        yield Static(f"Bubblewrap TUI\nVersion {version}", id="summary-header")
        yield Label("Command Preview", classes="section-label")
        yield Static(command_preview, id="command-preview", markup=True)
        yield Label("Summary", classes="section-label")
        yield Static(explanation, id="explanation", markup=True)
