"""UIField definitions for Network group."""

from model.ui_field import UIField


def _named(name: str, field: UIField) -> UIField:
    """Set the name attribute on a UIField and return it."""
    field.name = name
    return field


share_net = _named("share_net", UIField(
    bool, False, "opt-net",
    "Allow network", "Enable host network access",
    bwrap_flag="--share-net",
))

bind_resolv_conf = _named("bind_resolv_conf", UIField(
    bool, False, "opt-resolv-conf",
    "DNS config", "/etc/resolv.conf for hostname resolution",
    # bwrap_args handled by group's custom to_args
))

bind_ssl_certs = _named("bind_ssl_certs", UIField(
    bool, False, "opt-ssl-certs",
    "SSL certificates", "/etc/ssl/certs for HTTPS",
    # bwrap_args handled by group's custom to_args
))

# --- Network filter fields (synced to FilterList/PortList/FilterModeRadio widgets) ---
# Widget IDs are string literals to avoid circular import with ui.ids

network_mode = _named("network_mode", UIField(
    str, "off", "network-mode-radio",
    "Network mode", "Off/Filter/Audit",
))

hostname_mode = _named("hostname_mode", UIField(
    str, "off", "hostname-mode-radio",
    "Hostname filter mode", "Off/Whitelist/Blacklist",
))

hostname_hosts = _named("hostname_hosts", UIField(
    list, None, "hostname-list",
    "Filtered hostnames", "Hostnames to filter",
    default_factory=list,
))

ip_mode = _named("ip_mode", UIField(
    str, "off", "ip-mode-radio",
    "IP filter mode", "Off/Whitelist/Blacklist",
))

ip_cidrs = _named("ip_cidrs", UIField(
    list, None, "cidr-list",
    "Filtered CIDRs", "IP/CIDR ranges to filter",
    default_factory=list,
))

expose_ports = _named("expose_ports", UIField(
    list, None, "expose-port-list",
    "Expose ports", "Sandbox ports accessible to host",
    default_factory=list,
))

host_ports = _named("host_ports", UIField(
    list, None, "host-port-list",
    "Host ports", "Host ports accessible from sandbox",
    default_factory=list,
))
