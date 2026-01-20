"""Command output formatting for sandbox execution."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from model.network_filter import NetworkFilter


def print_execution_header(
    cmd: list[str],
    network_filter: "NetworkFilter | None" = None,
    sandbox_name: str | None = None,
    overlay_dirs: list[str] | None = None,
) -> None:
    """Print the execution header with command and optional details.

    Args:
        cmd: The bwrap command to display
        network_filter: Optional network filter config (if filtering enabled)
        sandbox_name: Optional sandbox name for overlay info
        overlay_dirs: Optional list of overlay directories
    """
    print("=" * 60)

    if network_filter and network_filter.requires_pasta():
        print("Executing (with network filtering):")
    else:
        print("Executing:")

    print(" ".join(cmd))

    if sandbox_name and overlay_dirs:
        print(f"\nSandbox: {sandbox_name}")
        print("Overlay writes will go to:")
        for d in overlay_dirs:
            print(f"  {d}/")

    if network_filter and network_filter.requires_pasta():
        # Show pasta command template
        print()
        pasta_parts = ["pasta", "--config-net", "--quiet", "--netns", "<netns>"]
        for port in network_filter.localhost_access.ports:
            pasta_parts.extend(["-T", str(port)])
        print(" ".join(pasta_parts))

        print("\nNetwork filtering:")
        if network_filter.hostname_filter.mode.value != "off":
            hosts = ", ".join(network_filter.hostname_filter.hosts) if network_filter.hostname_filter.hosts else "none"
            print(f"  Hostname {network_filter.hostname_filter.mode.value}: {hosts}")
        if network_filter.ip_filter.mode.value != "off":
            cidrs = ", ".join(network_filter.ip_filter.cidrs) if network_filter.ip_filter.cidrs else "none"
            print(f"  IP/CIDR {network_filter.ip_filter.mode.value}: {cidrs}")
        if network_filter.localhost_access.ports:
            ports = ", ".join(str(p) for p in network_filter.localhost_access.ports)
            print(f"  Localhost ports: {ports}")

    print("=" * 60 + "\n")
