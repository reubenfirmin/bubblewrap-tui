"""Network filtering event handlers."""

from __future__ import annotations

import logging
from typing import Any, Callable

log = logging.getLogger(__name__)


class NetworkEventsMixin:
    """Mixin for network filtering event handlers."""

    config: Any
    query_one: Callable
    _update_preview: Callable

    def _on_hostname_mode_change(self, mode: str) -> None:
        """Handle hostname filter mode change."""
        self.config._network_group.set("hostname_mode", mode)
        self._update_preview()

    def _on_hostname_add(self, hostname: str) -> None:
        """Handle hostname added to filter list."""
        # Already added by widget (shared list reference), just update preview
        self._update_preview()

    def _on_hostname_remove(self, hostname: str) -> None:
        """Handle hostname removed from filter list."""
        self._update_preview()

    def _on_ip_mode_change(self, mode: str) -> None:
        """Handle IP filter mode change."""
        self.config._network_group.set("ip_mode", mode)
        self._update_preview()

    def _on_cidr_add(self, cidr: str) -> None:
        """Handle CIDR added to filter list."""
        self._update_preview()

    def _on_cidr_remove(self, cidr: str) -> None:
        """Handle CIDR removed from filter list."""
        self._update_preview()

    def _on_expose_port_add(self, port: int) -> None:
        """Handle port added to expose ports list."""
        self._update_preview()

    def _on_expose_port_remove(self, port: int) -> None:
        """Handle port removed from expose ports list."""
        self._update_preview()

    def _on_host_port_add(self, port: int) -> None:
        """Handle port added to host ports list."""
        self._update_preview()

    def _on_host_port_remove(self, port: int) -> None:
        """Handle port removed from host ports list."""
        self._update_preview()
