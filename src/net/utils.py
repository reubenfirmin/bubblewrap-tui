"""Network filtering utilities."""

from __future__ import annotations

import ipaddress
import shutil
import socket
from pathlib import Path


def detect_distro() -> str | None:
    """Detect Linux distribution from /etc/os-release.

    Returns:
        Distribution ID (e.g., 'fedora', 'ubuntu', 'arch') or None if not detected.
    """
    os_release = Path("/etc/os-release")
    if not os_release.exists():
        return None

    try:
        content = os_release.read_text()
        for line in content.splitlines():
            if line.startswith("ID="):
                return line.split("=", 1)[1].strip().strip('"').lower()
    except OSError:
        pass
    return None


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
    except socket.gaierror:
        pass  # Host resolution failed

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
