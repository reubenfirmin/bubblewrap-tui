"""Network filtering tab composition."""

from __future__ import annotations

from typing import Callable, TYPE_CHECKING

from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.widgets import Label, RadioButton, RadioSet, Static

from model import groups
from model.network_filter import NetworkMode
from net import validate_cidr
from ui.widgets import FilterList, FilterModeRadio, OptionCard, PastaStatus, PortList
import ui.ids as ids

if TYPE_CHECKING:
    from model.network_filter import NetworkFilter


def compose_network_tab(
    network_filter: "NetworkFilter",
    share_net: bool,
    bind_resolv_conf: bool,
    bind_ssl_certs: bool,
    on_hostname_mode_change: Callable[[str], None],
    on_hostname_add: Callable[[str], None],
    on_hostname_remove: Callable[[str], None],
    on_ip_mode_change: Callable[[str], None],
    on_cidr_add: Callable[[str], None],
    on_cidr_remove: Callable[[str], None],
    on_expose_port_add: Callable[[int], None],
    on_expose_port_remove: Callable[[int], None],
    on_host_port_add: Callable[[int], None],
    on_host_port_remove: Callable[[int], None],
) -> ComposeResult:
    """Compose the network filtering tab content.

    Args:
        network_filter: NetworkFilter configuration object
        share_net: Whether full network access is enabled
        bind_resolv_conf: Whether DNS config is bound
        bind_ssl_certs: Whether SSL certs are bound
        on_hostname_mode_change: Callback when hostname filter mode changes
        on_hostname_add: Callback when hostname is added
        on_hostname_remove: Callback when hostname is removed
        on_ip_mode_change: Callback when IP filter mode changes
        on_cidr_add: Callback when CIDR is added
        on_cidr_remove: Callback when CIDR is removed
        on_expose_port_add: Callback when expose port is added
        on_expose_port_remove: Callback when expose port is removed
        on_host_port_add: Callback when host port is added
        on_host_port_remove: Callback when host port is removed

    Yields:
        Textual widgets for the network filtering tab
    """
    with VerticalScroll(id=ids.NETWORK_TAB_CONTENT):
        with Horizontal(id="options-grid"):
            # Left column: Network access + Full access options
            with Vertical(classes="options-column"):
                # Network access section
                with Container(classes="options-section"):
                    yield Label("Network Access", classes="section-label")
                    yield OptionCard(groups.share_net)
                    # Full access options (shown when share_net is enabled)
                    with Container(id="full-network-options", classes="" if share_net else "hidden"):
                        yield OptionCard(groups.bind_resolv_conf)
                        yield OptionCard(groups.bind_ssl_certs)

                # Network mode section
                with Container(classes="options-section"):
                    yield Label("Network Mode", classes="section-label")
                    with RadioSet(id=ids.NETWORK_MODE_RADIO):
                        yield RadioButton(
                            "Off",
                            value=network_filter.mode == NetworkMode.OFF,
                            id="network-mode-off",
                        )
                        yield RadioButton(
                            "Filter",
                            value=network_filter.mode == NetworkMode.FILTER,
                            id="network-mode-filter",
                        )
                        yield RadioButton(
                            "Audit",
                            value=network_filter.mode == NetworkMode.AUDIT,
                            id="network-mode-audit",
                        )
                    yield PastaStatus()
                    yield Static(
                        "Filter: block/allow traffic with iptables",
                        classes="network-hint",
                        id="filter-hint",
                    )
                    yield Static(
                        "Audit: capture traffic, show summary after exit",
                        classes="network-hint",
                        id="audit-hint",
                    )

                # Hostname filtering section (only for filter mode)
                with Container(id="filter-options", classes="" if network_filter.is_filter_mode() else "hidden"):
                    with Container(classes="options-section"):
                        yield Label("Hostname Filtering", classes="section-label")
                        yield Static(
                            "Filter by hostname (resolved once at launch):",
                            classes="network-hint",
                        )
                        yield Static(
                            "⚠ IPs resolved at startup. If DNS changes during "
                            "the session, new IPs will NOT be filtered.",
                            classes="network-warning",
                        )
                        yield FilterModeRadio(
                            mode=network_filter.hostname_filter.mode.value,
                            on_change=on_hostname_mode_change,
                            radio_id=ids.HOSTNAME_MODE_RADIO,
                        )
                        yield FilterList(
                            items=network_filter.hostname_filter.hosts,
                            on_add=on_hostname_add,
                            on_remove=on_hostname_remove,
                            placeholder="github.com",
                            list_id=ids.HOSTNAME_LIST,
                            input_id=ids.HOSTNAME_INPUT,
                            add_btn_id=ids.ADD_HOSTNAME_BTN,
                        )

            # Right column: IP/CIDR filtering + Port forwarding (only in filter mode)
            with Vertical(classes="options-column"):
                with Container(id="filter-options-right", classes="" if network_filter.is_filter_mode() else "hidden"):
                    # IP/CIDR filtering section
                    with Container(classes="options-section"):
                        yield Label("IP / CIDR Filtering", classes="section-label")
                        yield Static(
                            "Filter by IP or CIDR range (IPv4/IPv6):",
                            classes="network-hint",
                        )
                        yield FilterModeRadio(
                            mode=network_filter.ip_filter.mode.value,
                            on_change=on_ip_mode_change,
                            radio_id=ids.IP_MODE_RADIO,
                        )
                        yield FilterList(
                            items=network_filter.ip_filter.cidrs,
                            on_add=on_cidr_add,
                            on_remove=on_cidr_remove,
                            placeholder="10.0.0.0/8",
                            list_id=ids.CIDR_LIST,
                            input_id=ids.CIDR_INPUT,
                            add_btn_id=ids.ADD_CIDR_BTN,
                            validate_fn=validate_cidr,
                        )

                    # Expose ports section (sandbox → host)
                    with Container(classes="options-section"):
                        yield Label("Expose Ports (sandbox → host)", classes="section-label")
                        yield Static(
                            "Make sandbox servers accessible from host:",
                            classes="network-hint",
                        )
                        yield PortList(
                            ports=network_filter.port_forwarding.expose_ports,
                            on_add=on_expose_port_add,
                            on_remove=on_expose_port_remove,
                            list_id=ids.EXPOSE_PORT_LIST,
                            input_id=ids.EXPOSE_PORT_INPUT,
                            add_btn_id=ids.ADD_EXPOSE_PORT_BTN,
                        )

                    # Host ports section (host → sandbox)
                    with Container(classes="options-section"):
                        yield Label("Host Ports (host → sandbox)", classes="section-label")
                        yield Static(
                            "Access host services from sandbox:",
                            classes="network-hint",
                        )
                        yield PortList(
                            ports=network_filter.port_forwarding.host_ports,
                            on_add=on_host_port_add,
                            on_remove=on_host_port_remove,
                            list_id=ids.HOST_PORT_LIST,
                            input_id=ids.HOST_PORT_INPUT,
                            add_btn_id=ids.ADD_HOST_PORT_BTN,
                        )
