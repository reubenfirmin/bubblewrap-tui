"""Network filtering utilities."""

from __future__ import annotations

import ipaddress
import shutil
import socket


class HostnameResolutionError(Exception):
    """Raised when hostname resolution fails."""

    pass


def resolve_hostname(host: str) -> tuple[list[str], list[str]]:
    """Resolve hostname to IPv4 and IPv6 addresses.

    Args:
        host: Hostname to resolve (e.g., 'github.com')

    Returns:
        Tuple of (ipv4_list, ipv6_list) with deduplicated addresses.
    """
    ipv4: list[str] = []
    ipv6: list[str] = []

    try:
        # Get all address info (both IPv4 and IPv6)
        results = socket.getaddrinfo(host, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
        for family, _, _, _, sockaddr in results:
            ip = sockaddr[0]
            if family == socket.AF_INET:
                ipv4.append(ip)
            elif family == socket.AF_INET6:
                ipv6.append(ip)
    except socket.gaierror as e:
        raise HostnameResolutionError(f"Failed to resolve hostname '{host}': {e}")

    return (list(set(ipv4)), list(set(ipv6)))  # Dedupe


def get_www_variant(host: str) -> str | None:
    """Get the www variant of a hostname.

    Args:
        host: Hostname (e.g., 'github.com' or 'www.github.com')

    Returns:
        The www variant if host doesn't start with www.,
        the non-www variant if it does, or None if neither applies.
    """
    if host.startswith("www."):
        return host[4:]  # Strip www.
    elif "." in host and not host.startswith("www."):
        return f"www.{host}"  # Add www.
    return None


def is_ipv6(cidr: str) -> bool:
    """Check if CIDR is IPv6.

    Args:
        cidr: IP address or CIDR range string

    Returns:
        True if IPv6, False otherwise.
    """
    try:
        network = ipaddress.ip_network(cidr, strict=False)
        return network.version == 6
    except ValueError:
        return False


def validate_cidr(cidr: str) -> bool:
    """Validate if string is a valid CIDR or IP address.

    Args:
        cidr: IP address or CIDR range string

    Returns:
        True if valid, False otherwise.
    """
    try:
        ipaddress.ip_network(cidr, strict=False)
        return True
    except ValueError:
        return False


def validate_port(port: int | str) -> bool:
    """Validate if port number is valid.

    Args:
        port: Port number (int or string)

    Returns:
        True if valid port (1-65535), False otherwise.
    """
    try:
        port_int = int(port)
        return 1 <= port_int <= 65535
    except (ValueError, TypeError):
        return False


def find_cap_drop_tool() -> tuple[str | None, str]:
    """Find a tool to drop capabilities (setpriv or capsh).

    Returns:
        Tuple of (tool_path, shell_command_template).
        shell_command_template contains {command} placeholder for the user command.
        Returns (None, "") if no suitable tool is found.
    """
    # Prefer setpriv (from util-linux, more common)
    setpriv_path = shutil.which("setpriv")
    if setpriv_path:
        # setpriv expects capability names without "cap_" prefix
        # setpriv --bounding-set=-net_admin -- command args
        return (setpriv_path, 'exec setpriv --bounding-set=-net_admin -- {command}')

    # Fall back to capsh (from libcap)
    capsh_path = shutil.which("capsh")
    if capsh_path:
        # capsh --drop=cap_net_admin -- -c 'exec "$@"' -- command args
        return (capsh_path, 'exec capsh --drop=cap_net_admin -- -c \'exec "$@"\' -- {command}')

    return (None, "")


def validate_ip_for_shell(ip: str) -> str | None:
    """Validate and sanitize an IP address/CIDR for shell use.

    Defense-in-depth: re-validate IPs before interpolating into shell commands.
    While socket.getaddrinfo() should return safe values, this provides an
    additional layer of protection against shell injection.

    Args:
        ip: IP address or CIDR string

    Returns:
        The validated IP/CIDR string, or None if invalid.
    """
    try:
        # Parse as network to handle both plain IPs and CIDR notation
        network = ipaddress.ip_network(ip, strict=False)
        # Return the normalized string representation
        return str(network)
    except ValueError:
        return None
