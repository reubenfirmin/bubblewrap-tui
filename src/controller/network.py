"""Network filtering event handlers."""

from __future__ import annotations

import logging
from typing import Any, Callable

from model import FilterMode
from netfilter import get_www_variant
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
        # Auto-add www variant for transparency
        www_variant = get_www_variant(hostname)
        hosts = self.config.network_filter.hostname_filter.hosts
        if www_variant and www_variant not in hosts:
            hosts.append(www_variant)
            # Refresh the UI list to show the new item
            self._refresh_hostname_list()

        self._update_preview()

    def _refresh_hostname_list(self) -> None:
        """Refresh the hostname filter list UI."""
        try:
            from ui.widgets import FilterList

            filter_list = self.query_one(f"#{ids.HOSTNAME_LIST}", expect_type=None).parent
            if isinstance(filter_list, FilterList):
                filter_list.refresh_items(self.config.network_filter.hostname_filter.hosts)
        except Exception:
            pass  # UI not ready or element not found

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

    def _on_port_add(self, port: int) -> None:
        """Handle port added to localhost access list."""
        # Already added by widget, just update preview
        self._update_preview()

    def _on_port_remove(self, port: int) -> None:
        """Handle port removed from localhost access list."""
        # Already removed by widget, just update preview
        self._update_preview()
