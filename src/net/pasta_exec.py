"""pasta execution functions for sandbox network setup."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from model.network_filter import NetworkFilter
    from model.sandbox_config import SandboxConfig

from net.filtering import validate_filtering_requirements, create_init_script
from net.pasta_args import generate_pasta_args, prepare_bwrap_command
from net.utils import HostnameResolutionError

logger = logging.getLogger(__name__)


def execute_with_pasta(
    config: "SandboxConfig",
    file_map: dict[str, str] | None,
    build_command_fn: Callable[["SandboxConfig", dict[str, str] | None], list[str]],
    sandbox_name: str | None = None,
    overlay_dirs: list[str] | None = None,
) -> int:
    """Execute bwrap with network filtering via pasta spawn mode.

    pasta creates a new user+network namespace and runs bwrap inside.
    This is much simpler than the attach mode and requires no special privileges.

    Architecture:
        pasta --config-net -- bwrap [args] -- init_script

    The init script applies iptables rules, drops CAP_NET_ADMIN, then runs the user command.

    Args:
        config: SandboxConfig with network_filter enabled
        file_map: Optional file mapping for virtual user files
        build_command_fn: Function to build bwrap command from config
        sandbox_name: Optional sandbox name for overlay info
        overlay_dirs: Optional list of overlay directories

    Returns:
        Exit code from the sandboxed process
    """
    import os
    import sys

    nf = config.network_filter

    # Determine if we need to use seccomp for user namespace blocking
    # Use seccomp if explicitly enabled OR if network filtering + bwrap's disable_userns
    # (bwrap's --disable-userns prevents CAP_NET_ADMIN from working)
    use_seccomp = config.namespace.seccomp_block_userns or (
        nf.requires_pasta() and config.namespace.disable_userns
    )

    # Validate all required tools are available
    iptables_path, ip6tables_path, is_multicall, cap_drop_template = validate_filtering_requirements(nf)

    # Create init script (resolves hostnames to IPs)
    try:
        init_script_path = create_init_script(
            nf, config.command, iptables_path, ip6tables_path, is_multicall, cap_drop_template,
            use_seccomp=use_seccomp
        )
    except HostnameResolutionError as e:
        print("=" * 60, file=sys.stderr)
        print("Error: Hostname resolution failed", file=sys.stderr)
        print("", file=sys.stderr)
        print(str(e), file=sys.stderr)
        print("", file=sys.stderr)
        print("Network filtering requires all hostnames to resolve.", file=sys.stderr)
        print("Check your spelling and network connectivity.", file=sys.stderr)
        print("=" * 60, file=sys.stderr)
        sys.exit(1)

    tmp_dir = str(init_script_path.parent)

    # Build bwrap command with init script as the command
    original_command = config.command
    config.command = [str(init_script_path)]
    cmd = build_command_fn(config, file_map)
    config.command = original_command

    # Prepare command for pasta execution (removes --disable-userns if using seccomp)
    cmd = prepare_bwrap_command(cmd, tmp_dir, use_seccomp=use_seccomp)

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

    # Use execvp to replace this process with pasta
    # This gives clean terminal handling - pasta inherits our tty directly
    os.execvp("pasta", full_cmd)
    return 0  # Never reached


def execute_with_audit(
    config: "SandboxConfig",
    file_map: dict[str, str] | None,
    build_command_fn: Callable[["SandboxConfig", dict[str, str] | None], list[str]],
    sandbox_name: str | None = None,
    overlay_dirs: list[str] | None = None,
) -> int:
    """Execute bwrap with network auditing via pasta.

    Similar to execute_with_pasta but captures traffic instead of filtering.
    Uses subprocess instead of execvp so we can analyze the pcap after exit.

    Architecture:
        pasta --config-net --no-splice --pcap FILE -- bwrap [args]

    After the sandbox exits, parses the pcap and prints a summary of
    unique hosts/IPs that were contacted.

    Args:
        config: SandboxConfig with network_filter in audit mode
        file_map: Optional file mapping for virtual user files
        build_command_fn: Function to build bwrap command from config
        sandbox_name: Optional sandbox name for overlay info
        overlay_dirs: Optional list of overlay directories

    Returns:
        Exit code from the sandboxed process
    """
    import shutil
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
    cmd = build_command_fn(config, file_map)

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
            shutil.rmtree(tmp_dir)
        except Exception:
            pass

    return exit_code
