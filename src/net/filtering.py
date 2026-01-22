"""Network filtering validation and script generation."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from model.network_filter import NetworkFilter

from net.dns_proxy import generate_dns_proxy_script, get_dns_proxy_init_commands, needs_dns_proxy
from net.utils import find_cap_drop_tool


def validate_filtering_requirements(nf: "NetworkFilter") -> tuple[str, str | None, bool, str]:
    """Validate that all required tools are available for network filtering.

    Args:
        nf: NetworkFilter configuration

    Returns:
        Tuple of (iptables_path, ip6tables_path, is_multicall, cap_drop_template)

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

    # Check for capability drop tool
    cap_drop_tool, cap_drop_template = find_cap_drop_tool()
    if cap_drop_tool is None:
        print("=" * 60, file=sys.stderr)
        print("Error: No capability drop tool found", file=sys.stderr)
        print("", file=sys.stderr)
        print("Network filtering requires setpriv (util-linux) or capsh (libcap)", file=sys.stderr)
        print("to drop CAP_NET_ADMIN after setting up iptables rules.", file=sys.stderr)
        print("", file=sys.stderr)
        print("Install with:", file=sys.stderr)
        print("  Fedora/RHEL: sudo dnf install util-linux  (for setpriv)", file=sys.stderr)
        print("  Debian/Ubuntu: sudo apt install util-linux  (for setpriv)", file=sys.stderr)
        print("  Or: sudo apt install libcap2-bin  (for capsh)", file=sys.stderr)
        print("=" * 60, file=sys.stderr)
        sys.exit(1)

    return iptables_path, ip6tables_path, is_multicall, cap_drop_template


def create_init_script(
    nf: "NetworkFilter",
    user_command: list[str],
    iptables_path: str,
    ip6tables_path: str | None,
    is_multicall: bool,
    cap_drop_template: str,
    use_seccomp: bool = False,
) -> Path:
    """Create the init script that applies iptables rules then runs user command.

    Args:
        nf: NetworkFilter configuration
        user_command: The user's command to run
        iptables_path: Path to iptables binary
        ip6tables_path: Path to ip6tables binary (or None)
        is_multicall: Whether iptables is a multicall binary
        cap_drop_template: Template for capability drop command
        use_seccomp: Whether to apply seccomp filter blocking user namespaces

    Returns:
        Path to the created init script
    """
    import shlex
    import tempfile

    from net.iptables import generate_init_script

    tmp_dir = tempfile.mkdtemp(prefix="bui-net-")
    tmp_path = Path(tmp_dir)
    init_script_path = tmp_path / "init.sh"

    iptables_script = generate_init_script(nf, iptables_path, ip6tables_path, is_multicall)
    user_cmd = " ".join(shlex.quote(arg) for arg in user_command)
    exec_cmd = cap_drop_template.format(command=user_cmd)

    # Check if DNS proxy is needed for hostname filtering
    dns_proxy_setup = ""
    if needs_dns_proxy(nf.hostname_filter):
        dns_proxy_script_path = tmp_path / "dns_proxy.py"
        dns_proxy_script = generate_dns_proxy_script(nf.hostname_filter)
        dns_proxy_script_path.write_text(dns_proxy_script)
        dns_proxy_script_path.chmod(0o444)  # Read-only to prevent tampering
        dns_proxy_setup = get_dns_proxy_init_commands(str(dns_proxy_script_path))

        # Write resolv.conf to temp dir - will be ro-bind mounted by bwrap
        # This is more secure than creating it inside the sandbox
        resolv_conf_path = tmp_path / "resolv.conf"
        resolv_conf_path.write_text("# DNS handled by bubblewrap-tui DNS proxy\nnameserver 127.0.0.1\n")
        resolv_conf_path.chmod(0o444)

    # Build the final execution command
    # When using seccomp, we wrap the cap_drop+user_command with seccomp filter
    if use_seccomp:
        from seccomp import get_seccomp_init_commands
        seccomp_wrapper = get_seccomp_init_commands()
        # The seccomp wrapper reads SECCOMP_EXEC_CMD from environment
        # We set it to the cap_drop command (which will exec the user command)
        # Note: We need to escape the command for shell export
        escaped_exec_cmd = exec_cmd.replace("'", "'\"'\"'")  # Escape single quotes for shell
        final_exec = f"export SECCOMP_EXEC_CMD='{escaped_exec_cmd}'\n{seccomp_wrapper}"
    else:
        final_exec = exec_cmd

    init_wrapper = f'''#!/bin/sh
set -e

# Set up iptables rules
{iptables_script}
{dns_proxy_setup}
# Drop CAP_NET_ADMIN and run the user command
# This prevents the sandboxed process from modifying iptables rules
{final_exec}
'''

    init_script_path.write_text(init_wrapper)
    init_script_path.chmod(0o755)

    return init_script_path


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
