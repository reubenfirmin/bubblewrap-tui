"""iptables rule generation for network filtering."""

from __future__ import annotations

import logging
import os
import shutil
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from model.network_filter import NetworkFilter

logger = logging.getLogger(__name__)


def find_iptables() -> tuple[str | None, str | None, bool]:
    """Find iptables/ip6tables and determine if they're multi-call binaries.

    Returns:
        Tuple of (iptables_real_path, ip6tables_real_path, is_multicall).
        Paths are resolved (following symlinks). is_multicall is True if
        the binary is xtables-nft-multi or similar multi-call binary.
    """

    def resolve(name: str) -> str | None:
        path = shutil.which(name)
        if path is None:
            return None
        try:
            return os.path.realpath(path)
        except OSError:
            return path

    iptables = resolve("iptables")
    ip6tables = resolve("ip6tables")

    # Check if it's a multi-call binary (like xtables-nft-multi)
    is_multicall = iptables is not None and "multi" in iptables

    return (iptables, ip6tables, is_multicall)


def check_iptables() -> bool:
    """Check if iptables is available."""
    iptables, _, _ = find_iptables()
    return iptables is not None


def generate_iptables_rules(nf: NetworkFilter) -> tuple[list[str], list[str]]:
    """Generate iptables and ip6tables commands from filter config.

    Args:
        nf: NetworkFilter configuration

    Returns:
        Tuple of (iptables_rules, ip6tables_rules) as command strings.
    """
    from model.network_filter import FilterMode
    from net.utils import is_ipv6, resolve_hostname, validate_ip_for_shell

    v4_rules: list[str] = []
    v6_rules: list[str] = []

    # Always allow loopback
    v4_rules.append("iptables -A OUTPUT -o lo -j ACCEPT")
    v4_rules.append("iptables -A INPUT -i lo -j ACCEPT")
    v6_rules.append("ip6tables -A OUTPUT -o lo -j ACCEPT")
    v6_rules.append("ip6tables -A INPUT -i lo -j ACCEPT")

    # Collect all IPs to allow/block
    v4_allow: list[str] = []
    v6_allow: list[str] = []
    v4_block: list[str] = []
    v6_block: list[str] = []

    # Process hostname filter
    hf = nf.hostname_filter
    if hf.mode != FilterMode.OFF:
        for host in hf.hosts:
            ipv4s, ipv6s = resolve_hostname(host)
            if hf.mode == FilterMode.WHITELIST:
                v4_allow.extend(ipv4s)
                v6_allow.extend(ipv6s)
            else:  # BLACKLIST
                v4_block.extend(ipv4s)
                v6_block.extend(ipv6s)

    # Process IP filter
    ipf = nf.ip_filter
    if ipf.mode != FilterMode.OFF:
        for cidr in ipf.cidrs:
            if is_ipv6(cidr):
                if ipf.mode == FilterMode.WHITELIST:
                    v6_allow.append(cidr)
                else:
                    v6_block.append(cidr)
            else:
                if ipf.mode == FilterMode.WHITELIST:
                    v4_allow.append(cidr)
                else:
                    v4_block.append(cidr)

    # Defense-in-depth: validate all IPs before interpolating into shell commands
    # While socket.getaddrinfo() should return safe values, re-validate to prevent
    # any potential shell injection if the resolution path is compromised
    def safe_ip(ip: str) -> str | None:
        validated = validate_ip_for_shell(ip)
        if validated is None:
            logger.warning(f"Skipping invalid IP for iptables rule: {ip!r}")
        return validated

    # Generate rules - blacklist first (explicit blocks)
    for ip in v4_block:
        validated = safe_ip(ip)
        if validated:
            v4_rules.append(f"iptables -A OUTPUT -d {validated} -j DROP")
    for ip in v6_block:
        validated = safe_ip(ip)
        if validated:
            v6_rules.append(f"ip6tables -A OUTPUT -d {validated} -j DROP")

    # Then whitelist (explicit allows)
    for ip in v4_allow:
        validated = safe_ip(ip)
        if validated:
            v4_rules.append(f"iptables -A OUTPUT -d {validated} -j ACCEPT")
    for ip in v6_allow:
        validated = safe_ip(ip)
        if validated:
            v6_rules.append(f"ip6tables -A OUTPUT -d {validated} -j ACCEPT")

    # If any whitelist is active, drop everything else
    has_whitelist = hf.mode == FilterMode.WHITELIST or ipf.mode == FilterMode.WHITELIST
    if has_whitelist:
        v4_rules.append("iptables -A OUTPUT -j DROP")
        v6_rules.append("ip6tables -A OUTPUT -j DROP")

    return (v4_rules, v6_rules)


def generate_init_script(
    nf: NetworkFilter,
    iptables_path: str,
    ip6tables_path: str | None,
    is_multicall: bool,
) -> str:
    """Generate an init script that sets up iptables rules.

    This script is run inside the sandbox before the user command
    to set up network filtering rules.

    Args:
        nf: NetworkFilter configuration
        iptables_path: Resolved path to iptables binary
        ip6tables_path: Resolved path to ip6tables binary (may be None)
        is_multicall: True if the binary is a multi-call binary (like xtables-nft-multi)

    Returns:
        Shell script content as a string.
    """
    v4_rules, v6_rules = generate_iptables_rules(nf)

    lines = []

    # For multi-call binaries (xtables-nft-multi), invoke as: /path/to/binary iptables <args>
    # For regular binaries, invoke as: /path/to/iptables <args>
    if is_multicall:
        v4_cmd = f"{iptables_path} iptables"
        v6_cmd = f"{ip6tables_path} ip6tables" if ip6tables_path else None
    else:
        v4_cmd = iptables_path
        v6_cmd = ip6tables_path

    lines.append("# IPv4 rules")
    for rule in v4_rules:
        lines.append(rule.replace("iptables", v4_cmd))
    lines.append("")

    if v6_cmd and v6_rules:
        lines.append("# IPv6 rules")
        for rule in v6_rules:
            lines.append(rule.replace("ip6tables", v6_cmd))
        lines.append("")

    return "\n".join(lines)
