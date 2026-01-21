"""Network filtering model for controlling sandbox network access."""

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class NetworkMode(Enum):
    """Top-level network mode for sandbox."""

    OFF = "off"  # No network isolation via pasta
    FILTER = "filter"  # Network filtering with iptables rules
    AUDIT = "audit"  # Traffic auditing with pcap capture


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
class PortForwarding:
    """Bidirectional port forwarding between host and sandbox."""

    # Ports to expose from sandbox to host (-t)
    # Server in sandbox on port 8080 → accessible at host:8080
    expose_ports: list[int] = field(default_factory=list)

    # Ports to forward from host into sandbox (-T)
    # Host service on port 5432 → accessible in sandbox at localhost:5432
    host_ports: list[int] = field(default_factory=list)


@dataclass
class AuditConfig:
    """Configuration for network traffic auditing."""

    pcap_path: Path | None = None  # Auto-generated temp file if None


@dataclass
class NetworkFilter:
    """Top-level network config for a profile.

    Supports two modes via pasta:
    - FILTER: Network filtering with iptables rules
    - AUDIT: Traffic auditing with pcap capture (no filtering)

    Both modes use pasta to provide user-space networking in an
    isolated network namespace.
    """

    mode: NetworkMode = NetworkMode.OFF
    hostname_filter: HostnameFilter = field(default_factory=HostnameFilter)
    ip_filter: IPFilter = field(default_factory=IPFilter)
    port_forwarding: PortForwarding = field(default_factory=PortForwarding)
    audit: AuditConfig = field(default_factory=AuditConfig)

    @property
    def enabled(self) -> bool:
        """Returns True if filtering mode is enabled."""
        return self.mode == NetworkMode.FILTER

    @enabled.setter
    def enabled(self, value: bool) -> None:
        """Set filtering mode on/off."""
        self.mode = NetworkMode.FILTER if value else NetworkMode.OFF

    def requires_pasta(self) -> bool:
        """Returns True if pasta is needed for network isolation."""
        if self.mode == NetworkMode.OFF:
            return False
        if self.mode == NetworkMode.AUDIT:
            return True
        # FILTER mode - need pasta if any rules or port forwards
        return (
            self.hostname_filter.mode != FilterMode.OFF
            or self.ip_filter.mode != FilterMode.OFF
            or self.has_port_forwards()
        )

    def has_any_rules(self) -> bool:
        """Returns True if any filtering rules are configured."""
        return (
            self.hostname_filter.mode != FilterMode.OFF
            or self.ip_filter.mode != FilterMode.OFF
        )

    def has_port_forwards(self) -> bool:
        """Returns True if any port forwarding is configured."""
        return (
            len(self.port_forwarding.expose_ports) > 0
            or len(self.port_forwarding.host_ports) > 0
        )

    def is_audit_mode(self) -> bool:
        """Returns True if audit mode is enabled."""
        return self.mode == NetworkMode.AUDIT

    def is_filter_mode(self) -> bool:
        """Returns True if filter mode is enabled."""
        return self.mode == NetworkMode.FILTER

    def get_filtering_summary(self) -> list[str]:
        """Get human-readable summary lines for network filtering config."""
        lines = []
        if self.hostname_filter.mode.value != "off":
            mode = self.hostname_filter.mode.value
            hosts = ", ".join(self.hostname_filter.hosts) if self.hostname_filter.hosts else "none"
            lines.append(f"Hostname {mode}: {hosts}")
        if self.ip_filter.mode.value != "off":
            mode = self.ip_filter.mode.value
            cidrs = ", ".join(self.ip_filter.cidrs) if self.ip_filter.cidrs else "none"
            lines.append(f"IP/CIDR {mode}: {cidrs}")
        if self.port_forwarding.expose_ports:
            ports = ", ".join(str(p) for p in self.port_forwarding.expose_ports)
            lines.append(f"Expose ports (sandbox->host): {ports}")
        if self.port_forwarding.host_ports:
            ports = ", ".join(str(p) for p in self.port_forwarding.host_ports)
            lines.append(f"Host ports (host->sandbox): {ports}")
        return lines
