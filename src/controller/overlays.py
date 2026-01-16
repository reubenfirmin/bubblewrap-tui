"""Overlay event handlers."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable

from textual import on
from textual.containers import VerticalScroll
from textual.css.query import NoMatches
from textual.widgets import Button

if TYPE_CHECKING:
    from model import OverlayConfig


class OverlayEventsMixin:
    """Mixin for overlay-related event handlers."""

    config: Any
    query_one: Callable
    _update_preview: Callable
    _set_status: Callable
    _remove_overlay: Callable

    @on(Button.Pressed, "#add-overlay-btn")
    def on_add_overlay_pressed(self, event: Button.Pressed) -> None:
        """Add a new overlay."""
        self._add_overlay()

    def _add_overlay(self) -> None:
        """Add a new overlay configuration."""
        from model import OverlayConfig
        from ui import OverlayItem

        overlay = OverlayConfig(source="", dest="", mode="tmpfs")
        self.config.overlays.append(overlay)
        try:
            overlays_list = self.query_one("#overlays-list", VerticalScroll)
            overlays_list.mount(OverlayItem(overlay, self._update_preview, self._remove_overlay))
            # Show header when we have overlays
            self.query_one("#overlay-header").remove_class("hidden")
        except NoMatches:
            pass
        self._update_preview()
