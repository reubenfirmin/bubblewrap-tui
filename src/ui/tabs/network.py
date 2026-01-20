"""Network filtering tab composition."""

from __future__ import annotations

from typing import Callable, TYPE_CHECKING

from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.widgets import Checkbox, Label, RadioButton, RadioSet, Static

from model import groups
from netfilter import validate_cidr
from ui.widgets import FilterList, FilterModeRadio, OptionCard, PortList, SlirpStatus
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
    on_port_add: Callable[[int], None],
    on_port_remove: Callable[[int], None],
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
        on_port_add: Callback when port is added
        on_port_remove: Callback when port is removed

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

                # Filtered network section
                with Container(classes="options-section"):
                    yield Label("Network Filtering", classes="section-label")
                    yield Checkbox(
                        "Enable filtering (slirp4netns)",
                        value=network_filter.enabled,
                        id=ids.NETWORK_ENABLED,
                    )
                    yield SlirpStatus()
                    yield Static(
                        "Isolated network namespace with iptables rules.",
                        classes="network-hint",
                    )

                # Hostname filtering section
                with Container(id="filter-options", classes="" if network_filter.enabled else "hidden"):
                    with Container(classes="options-section"):
                        yield Label("Hostname Filtering", classes="section-label")
                        yield Static(
                            "Filter by hostname (resolved at launch):",
                            classes="network-hint",
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

            # Right column: IP/CIDR filtering + Localhost ports (only when filtering enabled)
            with Vertical(classes="options-column"):
                with Container(id="filter-options-right", classes="" if network_filter.enabled else "hidden"):
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

                    # Localhost access section
                    with Container(classes="options-section"):
                        yield Label("Localhost Port Forwarding", classes="section-label")
                        yield Static(
                            "Forward host ports into sandbox:",
                            classes="network-hint",
                        )
                        yield PortList(
                            ports=network_filter.localhost_access.ports,
                            on_add=on_port_add,
                            on_remove=on_port_remove,
                            list_id=ids.PORT_LIST,
                            input_id=ids.PORT_INPUT,
                            add_btn_id=ids.ADD_PORT_BTN,
                        )
