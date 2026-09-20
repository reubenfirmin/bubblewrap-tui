"""DNS addresses exposed by pasta inside a filtered network namespace."""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass
from pathlib import Path


class DNSConfigurationError(ValueError):
    """The host resolver cannot be used for sandbox DNS."""


@dataclass(frozen=True)
class DNSForwarding:
    # Each pair is (namespace address, host nameserver). Pasta supports one
    # mapping per address family. These addresses are reserved for DNS only.
    servers: tuple[tuple[str, str], ...]
    options: tuple[str, ...] = ()

    def resolv_conf(self, proxy: bool = False) -> str:
        addresses = ["127.0.0.1"] if proxy else [addr for addr, _ in self.servers]
        lines = ["# DNS forwarded to the host resolver by bubblewrap-tui"]
        lines.extend(f"nameserver {addr}" for addr in addresses)
        lines.extend(self.options)
        return "\n".join(lines) + "\n"


def read_dns_forwarding(path: Path | None = None) -> DNSForwarding:
    """Use the first host resolver of each family, preserving search options.

    In particular, a host loopback resolver must be contacted by pasta in the
    host namespace, not by a process using the sandbox's loopback interface.
    No public DNS service is substituted when host DNS is missing.
    """
    path = path or Path("/etc/resolv.conf")
    try:
        content = path.read_text()
    except OSError as exc:
        raise DNSConfigurationError(f"Cannot read host DNS configuration: {exc}") from exc

    servers = []
    families = set()
    options = []
    for line in content.splitlines():
        line = line.split("#", 1)[0].split(";", 1)[0].strip()
        parts = line.split()
        if not parts:
            continue
        if parts[0] == "nameserver":
            try:
                addr = ipaddress.ip_address(parts[1])
            except (IndexError, ValueError) as exc:
                raise DNSConfigurationError(f"Invalid host DNS entry: {line!r}") from exc
            if addr.is_unspecified or addr.is_multicast or getattr(addr, "scope_id", None):
                raise DNSConfigurationError(f"Unsupported host DNS address: {addr}")
            if addr.version not in families:
                alias = "169.254.53.53" if addr.version == 4 else "fd00::53"
                servers.append((alias, str(addr)))
                families.add(addr.version)
        elif parts[0] in ("search", "domain", "options"):
            options.append(line)

    if not servers:
        raise DNSConfigurationError("No DNS nameservers configured on host.")
    return DNSForwarding(tuple(servers), tuple(options))
