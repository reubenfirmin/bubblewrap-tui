"""pasta command argument generation."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from model.network_filter import NetworkFilter

logger = logging.getLogger(__name__)


def generate_pasta_args(nf: "NetworkFilter", pcap_path: Path | None = None) -> list[str]:
    """Generate pasta command arguments for spawn mode.

    In spawn mode, pasta creates a new user+network namespace and runs
    the given command inside. This is simpler than attach mode and
    doesn't require special privileges.

    Args:
        nf: NetworkFilter configuration
        pcap_path: Path for pcap capture (audit mode only)

    Returns:
        Command arguments for pasta (without the command to run).
    """
    args = [
        "pasta",
        "--config-net",  # Auto-configure networking
        "--foreground",  # Stay in foreground (default backgrounds, breaking terminal)
        "--quiet",  # Suppress output
    ]

    # Audit mode: capture traffic to pcap file
    if nf.is_audit_mode() and pcap_path:
        args.append("--no-splice")  # Force traffic through tap for capture
        args.extend(["--pcap", str(pcap_path)])

    # Expose sandbox ports to host (for servers running in sandbox)
    # -t makes sandbox port accessible on host (host:8080 → sandbox:8080)
    for port in nf.port_forwarding.expose_ports:
        args.extend(["-t", str(port)])

    # Forward host ports into sandbox (for accessing host services)
    # -T makes host port accessible in sandbox (sandbox:5432 → host:5432)
    for port in nf.port_forwarding.host_ports:
        args.extend(["-T", str(port)])

    # The "--" separator and command will be added by caller
    return args


def prepare_bwrap_command(cmd: list[str], tmp_dir: str, use_seccomp: bool = False) -> list[str]:
    """Prepare bwrap command for pasta execution.

    Modifies the command to:
    - Remove --unshare-net (pasta provides the namespace)
    - Add bind mount for temp directory
    - Add ro-bind for resolv.conf if DNS proxy is active
    - Remove --cap-drop CAP_NET_ADMIN (needed for iptables)
    - Add --cap-add CAP_NET_ADMIN
    - Remove --disable-userns if using seccomp alternative

    Args:
        cmd: The bwrap command list
        tmp_dir: Temp directory to bind mount
        use_seccomp: If True, remove --disable-userns (seccomp handles it instead)

    Returns:
        Modified command list
    """
    import sys

    # Remove --unshare-net since pasta provides the network namespace
    original_len = len(cmd)
    cmd = [arg for arg in cmd if arg != "--unshare-net"]
    if len(cmd) == original_len:
        logger.debug("--unshare-net not found in command, pasta may already handle namespace")

    # Remove --unshare-user since pasta provides the user namespace
    # bwrap's user namespace would be NESTED inside pasta's, and capabilities
    # in a nested user namespace cannot administer the parent's network namespace.
    # This is required for CAP_NET_ADMIN to work with iptables.
    cmd = [arg for arg in cmd if arg != "--unshare-user"]
    logger.debug("Removed --unshare-user, using pasta's user namespace for CAP_NET_ADMIN")

    # Also remove --uid and --gid since they require --unshare-user
    new_cmd: list[str] = []
    i = 0
    while i < len(cmd):
        if cmd[i] in ("--uid", "--gid") and i + 1 < len(cmd):
            i += 2  # Skip both the flag and its value
        else:
            new_cmd.append(cmd[i])
            i += 1
    cmd = new_cmd

    # Remove --disable-userns if using seccomp alternative
    # This is needed because bwrap's --disable-userns prevents CAP_NET_ADMIN from working
    if use_seccomp:
        cmd = [arg for arg in cmd if arg != "--disable-userns"]
        logger.debug("Removed --disable-userns, using seccomp filter instead")

    # Find the "--" separator and insert bind mount BEFORE it
    try:
        separator_idx = cmd.index("--")
        cmd.insert(separator_idx, "--bind")
        cmd.insert(separator_idx + 1, tmp_dir)
        cmd.insert(separator_idx + 2, tmp_dir)
    except ValueError:
        cmd.extend(["--bind", tmp_dir, tmp_dir])

    # If DNS proxy is active, ro-bind both the resolv.conf and the proxy script
    # This makes them completely immutable from inside the sandbox
    resolv_conf_path = Path(tmp_dir) / "resolv.conf"
    dns_proxy_path = Path(tmp_dir) / "dns_proxy.py"

    for filepath, dest in [
        (resolv_conf_path, "/etc/resolv.conf"),
        (dns_proxy_path, str(dns_proxy_path)),  # ro-bind in place
    ]:
        if filepath.exists():
            try:
                separator_idx = cmd.index("--")
                cmd.insert(separator_idx, "--ro-bind")
                cmd.insert(separator_idx + 1, str(filepath))
                cmd.insert(separator_idx + 2, dest)
            except ValueError:
                cmd.extend(["--ro-bind", str(filepath), dest])

    # Remove CAP_NET_ADMIN from drop_caps if present
    new_cmd: list[str] = []
    i = 0
    while i < len(cmd):
        if cmd[i] == "--cap-drop" and i + 1 < len(cmd) and cmd[i + 1] == "CAP_NET_ADMIN":
            i += 2  # Skip both --cap-drop and CAP_NET_ADMIN
        else:
            new_cmd.append(cmd[i])
            i += 1
    cmd = new_cmd

    # Add CAP_NET_ADMIN capability for iptables
    try:
        separator_idx = cmd.index("--")
        cmd.insert(separator_idx, "--cap-add")
        cmd.insert(separator_idx + 1, "CAP_NET_ADMIN")
    except ValueError:
        logger.error("No '--' separator found in bwrap command, cannot add CAP_NET_ADMIN")
        print("Error: malformed bwrap command (missing '--' separator)", file=sys.stderr)
        sys.exit(1)

    return cmd
