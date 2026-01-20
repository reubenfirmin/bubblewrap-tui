"""Network filtering model for controlling sandbox network access."""

from dataclasses import dataclass, field
from enum import Enum


class FilterMode(Enum):
    """Mode for network filtering."""

    OFF = "off"
    WHITELIST = "whitelist"
    BLACKLIST = "blacklist"


@dataclass
class HostnameFilter:
    """Filter by hostname (resolved to IPv4/IPv6 at launch)."""

    mode: FilterMode = FilterMode.OFF
    hosts: list[str] = field(default_factory=list)  # ["github.com", "registry.npmjs.org"]


@dataclass
class IPFilter:
    """Filter by IP address or CIDR range (IPv4 and IPv6)."""

    mode: FilterMode = FilterMode.OFF
    cidrs: list[str] = field(default_factory=list)  # ["10.0.0.0/8", "2001:db8::/32"]


@dataclass
class LocalhostAccess:
    """Ports to forward from host localhost into sandbox."""

    ports: list[int] = field(default_factory=list)  # [5432, 6379]


@dataclass
class NetworkFilter:
    """Top-level network filtering config for a profile.

    Network filtering uses slirp4netns to provide user-space networking
    with iptables rules for filtering. This allows true enforcement at
    the network level that applications cannot bypass.
    """

    enabled: bool = False
    hostname_filter: HostnameFilter = field(default_factory=HostnameFilter)
    ip_filter: IPFilter = field(default_factory=IPFilter)
    localhost_access: LocalhostAccess = field(default_factory=LocalhostAccess)

    def requires_slirp4netns(self) -> bool:
        """Returns True if any filtering is configured that needs slirp4netns."""
        return self.enabled and (
            self.hostname_filter.mode != FilterMode.OFF
            or self.ip_filter.mode != FilterMode.OFF
            or len(self.localhost_access.ports) > 0
        )

    def has_any_rules(self) -> bool:
        """Returns True if any filtering rules are configured."""
        return (
            self.hostname_filter.mode != FilterMode.OFF
            or self.ip_filter.mode != FilterMode.OFF
        )

    def has_port_forwards(self) -> bool:
        """Returns True if any localhost ports are forwarded."""
        return len(self.localhost_access.ports) > 0
