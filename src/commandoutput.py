"""Command output formatting for sandbox execution."""

from __future__ import annotations

import shlex
from pathlib import Path
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

    # Show the full command including pasta wrapper if network filtering
    if network_filter and network_filter.requires_pasta():
        from net.pasta_args import generate_pasta_args
        pasta_args = generate_pasta_args(network_filter)
        full_cmd = pasta_args + ["--"] + cmd
        print(shlex.join(full_cmd))
    else:
        print(shlex.join(cmd))

    if sandbox_name and overlay_dirs:
        print(f"\nSandbox: {sandbox_name}")
        print("Overlay writes will go to:")
        for d in overlay_dirs:
            print(f"  {d}/")

    if network_filter and network_filter.requires_pasta():
        # Show filtering summary
        summary_lines = network_filter.get_filtering_summary()
        if summary_lines:
            print("\nNetwork filtering:")
            for line in summary_lines:
                print(f"  {line}")

    print("=" * 60 + "\n")


def print_audit_header(
    cmd: list[str],
    pcap_path: Path,
    sandbox_name: str | None = None,
    overlay_dirs: list[str] | None = None,
) -> None:
    """Print the execution header for audit mode.

    Args:
        cmd: The bwrap command to display
        pcap_path: Path where pcap will be captured
        sandbox_name: Optional sandbox name for overlay info
        overlay_dirs: Optional list of overlay directories
    """
    print("=" * 60)
    print("Executing (with network auditing):")
    print(shlex.join(cmd))

    if sandbox_name and overlay_dirs:
        print(f"\nSandbox: {sandbox_name}")
        print("Overlay writes will go to:")
        for d in overlay_dirs:
            print(f"  {d}/")

    print("\nNetwork auditing enabled:")
    print(f"  Capturing traffic to: {pcap_path}")
    print("  Summary will be shown after sandbox exits.")

    print("=" * 60 + "\n")
