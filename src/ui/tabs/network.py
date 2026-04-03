"""Network filtering tab composition."""

from __future__ import annotations

from typing import Callable

from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.widgets import Label, RadioButton, RadioSet, Static

from model import groups
from model.network_filter import NetworkMode
from net import validate_cidr
from ui.widgets import FilterList, FilterModeRadio, OptionCard, PastaStatus, PortList
import ui.ids as ids


def compose_network_tab(
    network_mode: str,
    hostname_mode: str,
    hostname_hosts: list[str],
    ip_mode: str,
    ip_cidrs: list[str],
    expose_ports: list[int],
    host_ports: list[int],
    share_net: bool,
    has_dns: bool,
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
    """Compose the network filtering tab content."""
    is_filter = network_mode == NetworkMode.FILTER.value
    is_audit = network_mode == NetworkMode.AUDIT.value

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

                # Network mode section (only when network access enabled)
                with Container(id="network-mode-section", classes="" if share_net else "hidden"):
                    with Container(classes="options-section"):
                        yield Label("Network Mode", classes="section-label")
                        with RadioSet(id=ids.NETWORK_MODE_RADIO):
                            yield RadioButton(
                                "Direct",
                                value=(not is_filter and not is_audit),
                                id="network-mode-off",
                            )
                            yield RadioButton(
                                "Filter",
                                value=is_filter,
                                id="network-mode-filter",
                            )
                            yield RadioButton(
                                "Audit",
                                value=is_audit,
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
                with Container(id="filter-options", classes="" if is_filter else "hidden"):
                    with Container(classes="options-section"):
                        yield Label("Hostname Filtering", classes="section-label")
                        if has_dns:
                            yield Static(
                                "DNS proxy intercepts lookups at runtime",
                                classes="network-hint",
                            )
                            yield Static(
                                "example.com → matches example.com + subdomains\n"
                                "*.example.com → matches subdomains only",
                                classes="network-hint",
                            )
                            yield FilterModeRadio(
                                mode=hostname_mode,
                                on_change=on_hostname_mode_change,
                                radio_id=ids.HOSTNAME_MODE_RADIO,
                            )
                            yield FilterList(
                                items=hostname_hosts,
                                on_add=on_hostname_add,
                                on_remove=on_hostname_remove,
                                placeholder="github.com",
                                list_id=ids.HOSTNAME_LIST,
                                input_id=ids.HOSTNAME_INPUT,
                                add_btn_id=ids.ADD_HOSTNAME_BTN,
                            )
                        else:
                            yield Static(
                                "No DNS configured on host.\n"
                                "Hostname filtering unavailable.",
                                classes="network-hint warning",
                                id="no-dns-warning",
                            )

            # Right column: IP/CIDR filtering + Port forwarding (filter mode) or Audit info (audit mode)
            with Vertical(classes="options-column"):
                # Audit mode info card
                with Container(id="audit-options-right", classes="" if is_audit else "hidden"):
                    with Container(classes="options-section"):
                        yield Label("Audit Mode", classes="section-label")
                        yield Static(
                            "Network traffic will be captured to a PCAP file while "
                            "the sandbox is running.\n\n"
                            "When the process exits, traffic will be analyzed and a "
                            "summary of contacted hosts and IPs will be displayed.\n\n"
                            "Use this to discover what network connections an "
                            "application makes before deciding on filter rules.",
                            classes="audit-info-text",
                        )

                # Filter mode options
                with Container(id="filter-options-right", classes="" if is_filter else "hidden"):
                    # IP/CIDR filtering section
                    with Container(classes="options-section"):
                        yield Label("IP / CIDR Filtering", classes="section-label")
                        yield Static(
                            "Filter by IP or CIDR range (IPv4/IPv6):",
                            classes="network-hint",
                        )
                        yield FilterModeRadio(
                            mode=ip_mode,
                            on_change=on_ip_mode_change,
                            radio_id=ids.IP_MODE_RADIO,
                        )
                        yield FilterList(
                            items=ip_cidrs,
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
                            "Make sandbox servers accessible to host:",
                            classes="network-hint",
                        )
                        yield PortList(
                            ports=expose_ports,
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
                            ports=host_ports,
                            on_add=on_host_port_add,
                            on_remove=on_host_port_remove,
                            list_id=ids.HOST_PORT_LIST,
                            input_id=ids.HOST_PORT_INPUT,
                            add_btn_id=ids.ADD_HOST_PORT_BTN,
                        )
