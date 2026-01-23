"""Network filtering validation and script generation."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from model.network_filter import NetworkFilter

from fileutils import write_file_atomic
from net.dns_proxy import generate_dns_proxy_script, get_dns_proxy_init_commands, needs_dns_proxy


def validate_filtering_requirements(nf: "NetworkFilter") -> tuple[str, str | None, bool]:
    """Validate that all required tools are available for network filtering.

    Args:
        nf: NetworkFilter configuration

    Returns:
        Tuple of (iptables_path, ip6tables_path, is_multicall)

    Raises:
        SystemExit: If required tools are not found
    """
    from model.network_filter import FilterMode
    from net.iptables import find_iptables

    # Check iptables availability
    iptables_path, ip6tables_path, is_multicall = find_iptables()
    if iptables_path is None:
        print("=" * 60, file=sys.stderr)
        print("Error: iptables not found", file=sys.stderr)
        print("", file=sys.stderr)
        print("Network filtering requires iptables.", file=sys.stderr)
        print("Install with your package manager (e.g. iptables, nftables)", file=sys.stderr)
        print("=" * 60, file=sys.stderr)
        sys.exit(1)

    # Check if IPv6 filtering is needed but ip6tables is unavailable
    has_ipv6_filtering = False
    if nf.hostname_filter.mode != FilterMode.OFF:
        has_ipv6_filtering = True
    if nf.ip_filter.mode != FilterMode.OFF:
        from net.utils import is_ipv6
        has_ipv6_filtering = has_ipv6_filtering or any(is_ipv6(cidr) for cidr in nf.ip_filter.cidrs)

    if has_ipv6_filtering and ip6tables_path is None:
        print("=" * 60, file=sys.stderr)
        print("Error: ip6tables not found", file=sys.stderr)
        print("", file=sys.stderr)
        print("IPv6 filtering rules cannot be applied.", file=sys.stderr)
        print("Install ip6tables or disable IPv6 filtering.", file=sys.stderr)
        print("=" * 60, file=sys.stderr)
        sys.exit(1)

    return iptables_path, ip6tables_path, is_multicall


def create_wrapper_script(
    nf: "NetworkFilter",
    bwrap_cmd: list[str],
    iptables_path: str,
    ip6tables_path: str | None,
    is_multicall: bool,
    tmp_path: Path | None = None,
) -> Path:
    """Create the wrapper script that runs iptables/DNS setup then execs bwrap.

    This script runs BEFORE bwrap (in pasta's namespace), which allows bwrap
    to use --unshare-user --disable-userns for full namespace isolation.

    Architecture:
        pasta -- wrapper.sh
                    |-> iptables rules (needs CAP_NET_ADMIN)
                    |-> DNS proxy start (needs port 53 binding)
                    |-> exec bwrap --unshare-user --disable-userns ... -- user_cmd

    Args:
        nf: NetworkFilter configuration
        bwrap_cmd: The complete bwrap command to exec
        iptables_path: Path to iptables binary
        ip6tables_path: Path to ip6tables binary (or None)
        is_multicall: Whether iptables is a multicall binary
        tmp_path: Optional temp directory to use. If None, creates a new one.

    Returns:
        Path to the created wrapper script
    """
    import shlex
    import tempfile

    from net.iptables import generate_init_script

    if tmp_path is None:
        tmp_dir = tempfile.mkdtemp(prefix="bui-net-")
        tmp_path = Path(tmp_dir)

    wrapper_script_path = tmp_path / "wrapper.sh"

    iptables_script = generate_init_script(nf, iptables_path, ip6tables_path, is_multicall)

    # Check if DNS proxy is needed for hostname filtering
    dns_proxy_setup = ""
    if needs_dns_proxy(nf.hostname_filter):
        dns_proxy_script_path = tmp_path / "dns_proxy.py"
        dns_proxy_script = generate_dns_proxy_script(nf.hostname_filter)
        write_file_atomic(dns_proxy_script_path, dns_proxy_script, 0o755)
        dns_proxy_setup = get_dns_proxy_init_commands(str(dns_proxy_script_path))

        # Write resolv.conf to temp dir - will be ro-bind mounted by bwrap
        resolv_conf_path = tmp_path / "resolv.conf"
        write_file_atomic(resolv_conf_path, "# DNS handled by bubblewrap-tui DNS proxy\nnameserver 127.0.0.1\n", 0o444)

    # Build the bwrap command string
    bwrap_cmd_str = " ".join(shlex.quote(arg) for arg in bwrap_cmd)

    wrapper_script = f'''#!/bin/sh
set -e

# Set up iptables rules (requires CAP_NET_ADMIN from pasta)
{iptables_script}
{dns_proxy_setup}
# Execute bwrap with full namespace isolation
# --unshare-user creates nested user namespace
# --disable-userns blocks further namespace creation (prevents escapes)
exec {bwrap_cmd_str}
'''

    write_file_atomic(wrapper_script_path, wrapper_script, 0o755)

    return wrapper_script_path


def uses_dns_proxy(nf: "NetworkFilter") -> bool:
    """Check if the network filter configuration will use the DNS proxy.

    This is used by other modules to determine if they should skip
    binding the host's /etc/resolv.conf (since the DNS proxy creates its own).

    Args:
        nf: NetworkFilter configuration

    Returns:
        True if DNS proxy will be used
    """
    return needs_dns_proxy(nf.hostname_filter)
