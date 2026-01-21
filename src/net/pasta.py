"""pasta network namespace wrapper.

pasta (part of passt) provides user-mode networking for sandboxes.
It creates a network namespace and provides connectivity without
requiring special privileges.

In spawn mode, pasta creates a new user+network namespace and runs
the given command inside. This is simpler than slirp4netns and
requires no CAP_SYS_ADMIN.
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from model.network_filter import NetworkFilter
    from model.config import SandboxConfig

from net.utils import detect_distro, find_cap_drop_tool

logger = logging.getLogger(__name__)


def check_pasta() -> bool:
    """Check if pasta is installed."""
    return shutil.which("pasta") is not None


def get_install_instructions() -> str:
    """Return distro-specific install instructions for pasta (passt package)."""
    distro = detect_distro()

    instructions = {
        "fedora": "sudo dnf install passt",
        "rhel": "sudo dnf install passt",
        "centos": "sudo dnf install passt",
        "debian": "sudo apt install passt",
        "ubuntu": "sudo apt install passt",
        "arch": "sudo pacman -S passt",
        "manjaro": "sudo pacman -S passt",
        "opensuse": "sudo zypper install passt",
        "opensuse-leap": "sudo zypper install passt",
        "opensuse-tumbleweed": "sudo zypper install passt",
        "gentoo": "sudo emerge passt",
        "alpine": "sudo apk add passt",
        "void": "sudo xbps-install passt",
        "nixos": "nix-env -iA nixpkgs.passt",
    }

    if distro in instructions:
        return instructions[distro]

    # Fallback - check for package manager
    if shutil.which("apt"):
        return "sudo apt install passt"
    elif shutil.which("dnf"):
        return "sudo dnf install passt"
    elif shutil.which("pacman"):
        return "sudo pacman -S passt"
    elif shutil.which("zypper"):
        return "sudo zypper install passt"

    return "Install passt using your package manager"


def get_pasta_status() -> tuple[bool, str]:
    """Get pasta installation status and install command.

    Returns:
        Tuple of (is_installed, install_command_or_status_message).
    """
    if check_pasta():
        return (True, "pasta installed")
    else:
        return (False, get_install_instructions())


def generate_pasta_args(nf: NetworkFilter, pcap_path: Path | None = None) -> list[str]:
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
        "--quiet",  # Suppress output
    ]

    # Audit mode: capture traffic to pcap file
    if nf.is_audit_mode() and pcap_path:
        args.append("--no-splice")  # Force traffic through tap for capture
        args.extend(["--pcap", str(pcap_path)])

    # Expose sandbox ports to host (for servers running in sandbox)
    # -t forwards TCP ports from host to sandbox
    for port in nf.port_forwarding.expose_ports:
        args.extend(["-t", str(port)])

    # Forward host ports into sandbox (for accessing host services)
    # -T forwards TCP ports from sandbox to host localhost
    for port in nf.port_forwarding.host_ports:
        args.extend(["-T", str(port)])

    # The "--" separator and command will be added by caller
    return args


def execute_with_pasta(
    config: "SandboxConfig",
    fd_map: dict[str, int] | None,
    build_command_fn: Callable[["SandboxConfig", dict[str, int] | None], list[str]],
    sandbox_name: str | None = None,
    overlay_dirs: list[str] | None = None,
) -> None:
    """Execute bwrap with network filtering via pasta spawn mode.

    pasta creates a new user+network namespace and runs bwrap inside.
    This is much simpler than the attach mode and requires no special privileges.

    Architecture:
        pasta --config-net -- bwrap [args] -- init_script

    The init script applies iptables rules, drops CAP_NET_ADMIN, then runs the user command.

    Args:
        config: SandboxConfig with network_filter enabled
        fd_map: Optional FD mapping for virtual user files
        build_command_fn: Function to build bwrap command from config
        sandbox_name: Optional sandbox name for overlay info
        overlay_dirs: Optional list of overlay directories
    """
    import os
    import shlex
    import sys
    import tempfile

    from model.network_filter import FilterMode
    from net.iptables import find_iptables, generate_init_script

    nf = config.network_filter

    # Fail fast: check iptables availability
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
        # Hostname filter may resolve to IPv6 addresses
        has_ipv6_filtering = True
    if nf.ip_filter.mode != FilterMode.OFF:
        from net.utils import is_ipv6
        has_ipv6_filtering = has_ipv6_filtering or any(is_ipv6(cidr) for cidr in nf.ip_filter.cidrs)

    if has_ipv6_filtering and ip6tables_path is None:
        print("=" * 60, file=sys.stderr)
        print("Warning: ip6tables not found", file=sys.stderr)
        print("", file=sys.stderr)
        print("IPv6 filtering rules will NOT be applied.", file=sys.stderr)
        print("IPv6 traffic may bypass the filter.", file=sys.stderr)
        print("Install ip6tables or ensure your iptables supports IPv6.", file=sys.stderr)
        print("=" * 60, file=sys.stderr)

    # Check for capability drop tool (setpriv or capsh)
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

    # Create temp directory for scripts
    tmp_dir = tempfile.mkdtemp(prefix="bui-net-")
    tmp_path = Path(tmp_dir)
    init_script_path = tmp_path / "init.sh"

    # Generate iptables init script content
    iptables_script = generate_init_script(nf, iptables_path, ip6tables_path, is_multicall)

    # Build the user command as a shell-safe string
    user_cmd = " ".join(shlex.quote(arg) for arg in config.command)

    # Build the final exec command that drops CAP_NET_ADMIN before running user command
    # This ensures the sandboxed process cannot modify/disable the iptables rules
    exec_cmd = cap_drop_template.format(command=user_cmd)

    # Create the init script that applies iptables rules then runs user command
    # pasta --config-net already sets up the network interface before running bwrap
    init_wrapper = f'''#!/bin/sh
set -e

# Set up iptables rules
{iptables_script}

# Drop CAP_NET_ADMIN and run the user command
# This prevents the sandboxed process from modifying iptables rules
{exec_cmd}
'''

    init_script_path.write_text(init_wrapper)
    init_script_path.chmod(0o755)

    # Build bwrap command - pasta provides network namespace, so remove --unshare-net
    original_command = config.command
    config.command = [str(init_script_path)]

    cmd = build_command_fn(config, fd_map)
    config.command = original_command

    # Remove --unshare-net since pasta provides the network namespace
    # Use list filtering to handle multiple occurrences robustly
    original_len = len(cmd)
    cmd = [arg for arg in cmd if arg != "--unshare-net"]
    if len(cmd) == original_len:
        logger.debug("--unshare-net not found in command, pasta may already handle namespace")

    # Find the "--" separator and insert bind mount BEFORE it
    try:
        separator_idx = cmd.index("--")
        cmd.insert(separator_idx, "--bind")
        cmd.insert(separator_idx + 1, tmp_dir)
        cmd.insert(separator_idx + 2, tmp_dir)
    except ValueError:
        cmd.extend(["--bind", tmp_dir, tmp_dir])

    # Remove CAP_NET_ADMIN from drop_caps if present
    # Use proper iteration to handle the --cap-drop CAP_NET_ADMIN pair correctly
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
    # The separator must exist (bwrap requires it), but handle defensively
    try:
        separator_idx = cmd.index("--")
        cmd.insert(separator_idx, "--cap-add")
        cmd.insert(separator_idx + 1, "CAP_NET_ADMIN")
    except ValueError:
        # Should never happen with valid bwrap commands, but fail gracefully
        logger.error("No '--' separator found in bwrap command, cannot add CAP_NET_ADMIN")
        print("Error: malformed bwrap command (missing '--' separator)", file=sys.stderr)
        sys.exit(1)

    # Print header
    from commandoutput import print_execution_header
    print_execution_header(
        cmd,
        network_filter=nf,
        sandbox_name=sandbox_name,
        overlay_dirs=overlay_dirs,
    )

    # Build pasta command: pasta [args] -- bwrap [args]
    pasta_args = generate_pasta_args(nf)
    full_cmd = pasta_args + ["--"] + cmd

    # Execute: pasta spawns bwrap in the network namespace it creates
    os.execvp("pasta", full_cmd)


def execute_with_audit(
    config: "SandboxConfig",
    fd_map: dict[str, int] | None,
    build_command_fn: Callable[["SandboxConfig", dict[str, int] | None], list[str]],
    sandbox_name: str | None = None,
    overlay_dirs: list[str] | None = None,
) -> None:
    """Execute bwrap with network auditing via pasta.

    Similar to execute_with_pasta but captures traffic instead of filtering.
    Uses subprocess instead of execvp so we can analyze the pcap after exit.

    Architecture:
        pasta --config-net --no-splice --pcap FILE -- bwrap [args]

    After the sandbox exits, parses the pcap and prints a summary of
    unique hosts/IPs that were contacted.

    Args:
        config: SandboxConfig with network_filter in audit mode
        fd_map: Optional FD mapping for virtual user files
        build_command_fn: Function to build bwrap command from config
        sandbox_name: Optional sandbox name for overlay info
        overlay_dirs: Optional list of overlay directories
    """
    import subprocess
    import sys
    import tempfile

    from net.audit import parse_pcap, print_audit_summary

    nf = config.network_filter

    # Create temp directory for pcap file
    # Use a directory that pasta can write to (it drops privileges)
    tmp_dir = tempfile.mkdtemp(prefix="bui-audit-")
    tmp_path = Path(tmp_dir)

    # Make directory world-writable for pasta's dropped privileges
    tmp_path.chmod(0o777)

    pcap_path = nf.audit.pcap_path or (tmp_path / "audit.pcap")

    # Build bwrap command
    cmd = build_command_fn(config, fd_map)

    # Remove --unshare-net since pasta provides the network namespace
    cmd = [arg for arg in cmd if arg != "--unshare-net"]

    # Print header
    from commandoutput import print_audit_header
    print_audit_header(
        cmd,
        pcap_path=pcap_path,
        sandbox_name=sandbox_name,
        overlay_dirs=overlay_dirs,
    )

    # Build pasta command with audit options
    pasta_args = generate_pasta_args(nf, pcap_path)
    full_cmd = pasta_args + ["--"] + cmd

    # Execute with subprocess so we can post-process
    try:
        result = subprocess.run(full_cmd)
        exit_code = result.returncode
    except KeyboardInterrupt:
        print("\nInterrupted by user")
        exit_code = 130

    # Parse and display audit results
    if pcap_path.exists():
        try:
            audit_result = parse_pcap(pcap_path)
            print_audit_summary(audit_result, pcap_path)
        except Exception as e:
            print(f"\nWarning: Failed to parse pcap: {e}", file=sys.stderr)
    else:
        # Clean up empty temp directory if no pcap was created
        try:
            import shutil
            shutil.rmtree(tmp_dir)
        except Exception:
            pass

    sys.exit(exit_code)
