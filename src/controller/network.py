"""Network filtering event handlers."""

from __future__ import annotations

import logging
from typing import Any, Callable

from model import FilterMode
import ui.ids as ids

log = logging.getLogger(__name__)


class NetworkEventsMixin:
    """Mixin for network filtering event handlers."""

    config: Any
    query_one: Callable
    _update_preview: Callable

    def _on_hostname_mode_change(self, mode: str) -> None:
        """Handle hostname filter mode change."""
        self.config.network_filter.hostname_filter.mode = FilterMode(mode)
        self._update_preview()

    def _on_hostname_add(self, hostname: str) -> None:
        """Handle hostname added to filter list."""
        # Hostname matching is handled by DNS proxy:
        # - "example.com" matches example.com and all subdomains (www.example.com, api.example.com)
        # - "*.example.com" matches only subdomains, not example.com itself
        self._update_preview()

    def _on_hostname_remove(self, hostname: str) -> None:
        """Handle hostname removed from filter list."""
        # Already removed by widget, just update preview
        self._update_preview()

    def _on_ip_mode_change(self, mode: str) -> None:
        """Handle IP filter mode change."""
        self.config.network_filter.ip_filter.mode = FilterMode(mode)
        self._update_preview()

    def _on_cidr_add(self, cidr: str) -> None:
        """Handle CIDR added to filter list."""
        # Already added by widget, just update preview
        self._update_preview()

    def _on_cidr_remove(self, cidr: str) -> None:
        """Handle CIDR removed from filter list."""
        # Already removed by widget, just update preview
        self._update_preview()

    def _on_expose_port_add(self, port: int) -> None:
        """Handle port added to expose ports list."""
        # Already added by widget, just update preview
        self._update_preview()

    def _on_expose_port_remove(self, port: int) -> None:
        """Handle port removed from expose ports list."""
        # Already removed by widget, just update preview
        self._update_preview()

    def _on_host_port_add(self, port: int) -> None:
        """Handle port added to host ports list."""
        # Already added by widget, just update preview
        self._update_preview()

    def _on_host_port_remove(self, port: int) -> None:
        """Handle port removed from host ports list."""
        # Already removed by widget, just update preview
        self._update_preview()
