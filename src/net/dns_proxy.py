"""DNS proxy generation for dynamic hostname filtering.

This module generates a lightweight Python DNS proxy script that runs inside
the sandbox to intercept DNS requests. Unlike static IP-based filtering,
this approach handles IP rotation (CDNs, load balancers) by filtering at
the DNS layer.

Architecture:
    pasta --config-net -- bwrap -- init.sh
                                     |
                                     v
                            1. Apply iptables rules
                            2. Write DNS proxy script to /tmp
                            3. Start proxy on 127.0.0.1:53
                            4. Override /etc/resolv.conf -> nameserver 127.0.0.1
                            5. Drop CAP_NET_ADMIN
                            6. exec user command
"""

from __future__ import annotations

import ipaddress
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from model.network_filter import HostnameFilter


def _validate_dns_server(addr: str) -> str:
    """Validate that addr is a valid IP address.

    This prevents code injection via malicious /etc/resolv.conf entries
    being interpolated into the generated DNS proxy script.

    Args:
        addr: String that should be an IP address

    Returns:
        The validated address string

    Raises:
        ValueError: If addr is not a valid IPv4 or IPv6 address
    """
    try:
        ipaddress.ip_address(addr)
        return addr
    except ValueError:
        raise ValueError(f"Invalid DNS server address: {addr!r}")


def _load_dns_proxy_script() -> str:
    """Load the DNS proxy script template from file.

    In development, reads from dns_proxy_script.py.
    In bundled mode, DNS_PROXY_SCRIPT is inlined by build.py.
    """
    # This will be replaced by build.py with the actual script content
    script_path = Path(__file__).parent / "dns_proxy_script.py"
    return script_path.read_text()


# Loaded at import time (or inlined by build.py)
DNS_PROXY_SCRIPT = _load_dns_proxy_script()


def get_host_nameservers() -> list[str]:
    """Read nameservers from the host's /etc/resolv.conf.

    Returns:
        List of nameserver IPs. Empty list if none found (no fallback).

    Note:
        Localhost entries (e.g., 127.0.0.53 for systemd-resolved) are included.
        The DNS proxy runs inside the sandbox's network namespace, so there's
        no loop - the sandbox's 127.0.0.1:53 is separate from the host's resolver.
    """
    resolv_conf = Path("/etc/resolv.conf")
    nameservers = []

    try:
        if resolv_conf.exists():
            content = resolv_conf.read_text()
            # Match "nameserver <ip>" lines
            for line in content.splitlines():
                line = line.strip()
                if line.startswith("nameserver"):
                    parts = line.split()
                    if len(parts) >= 2:
                        nameservers.append(parts[1])
    except OSError:
        pass

    return nameservers


def has_host_dns() -> bool:
    """Check if the host has DNS configured.

    Returns:
        True if at least one nameserver is configured.
    """
    return len(get_host_nameservers()) > 0


def generate_dns_proxy_script(
    hostname_filter: "HostnameFilter",
    upstream_dns: str | None = None,
    upstream_port: int = 53,
) -> str:
    """Generate a DNS proxy script configured for the given hostname filter.

    Args:
        hostname_filter: HostnameFilter configuration with mode and hosts
        upstream_dns: Upstream DNS server IP (default: read from host's resolv.conf)
        upstream_port: Upstream DNS port (default: 53)

    Returns:
        Complete Python script as a string, ready to be written to a file

    Raises:
        ValueError: If no upstream DNS is available or if the DNS address is invalid
    """
    from model.network_filter import FilterMode

    mode = "whitelist" if hostname_filter.mode == FilterMode.WHITELIST else "blacklist"
    hosts = hostname_filter.hosts

    # Use host's DNS if not specified
    if upstream_dns is None:
        nameservers = get_host_nameservers()
        if not nameservers:
            raise ValueError(
                "No DNS nameservers configured on host. "
                "Hostname filtering requires working DNS."
            )
        upstream_dns = nameservers[0]

    # Validate DNS address to prevent code injection via malicious resolv.conf
    upstream_dns = _validate_dns_server(upstream_dns)

    return DNS_PROXY_SCRIPT.format(
        upstream_dns=upstream_dns,
        upstream_port=upstream_port,
        mode=mode,
        hosts=repr(hosts),
    )


def get_dns_proxy_init_commands(proxy_script_path: str) -> str:
    """Generate shell commands to start the DNS proxy in the init script.

    This sets up the DNS proxy before dropping CAP_NET_ADMIN:
    1. Start the proxy in background
    2. Wait for proxy to be ready

    Note: resolv.conf is ro-bind mounted by bwrap, not created here.
    This is more secure as the sandboxed process cannot modify it.

    Args:
        proxy_script_path: Path where the proxy script will be written (e.g., /tmp/dns_proxy.py)

    Returns:
        Shell commands as a string to embed in init.sh
    """
    return f'''
# DNS Proxy Setup
# Note: /etc/resolv.conf is ro-bind mounted by bwrap pointing to 127.0.0.1

# Start DNS proxy in background
python3 {proxy_script_path} &
DNS_PROXY_PID=$!

# Give proxy time to bind (port 53 binding is fast)
sleep 0.1

# Verify proxy is running
if ! kill -0 $DNS_PROXY_PID 2>/dev/null; then
    echo "Error: DNS proxy failed to start" >&2
    exit 1
fi
'''


def needs_dns_proxy(hostname_filter: "HostnameFilter") -> bool:
    """Check if DNS proxy is needed for the given hostname filter.

    Args:
        hostname_filter: HostnameFilter configuration

    Returns:
        True if DNS proxy should be used (hostname filtering is active)
    """
    from model.network_filter import FilterMode

    return hostname_filter.mode != FilterMode.OFF and len(hostname_filter.hosts) > 0
