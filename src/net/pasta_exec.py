"""pasta execution functions for sandbox network setup."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from model.network_filter import NetworkFilter
    from model.sandbox_config import SandboxConfig

from command_execution import _run_with_pty
from net.filtering import create_wrapper_script, validate_filtering_requirements
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

    pasta creates a new user+network namespace and runs a wrapper script inside.
    The wrapper applies iptables rules, starts DNS proxy if needed, then execs bwrap.

    This architecture allows bwrap to use --unshare-user --disable-userns for full
    namespace isolation, because iptables runs BEFORE bwrap (doesn't need CAP_NET_ADMIN
    inside the sandbox).

    Architecture:
        pasta --config-net -- wrapper.sh
                                 |-> iptables rules
                                 |-> start DNS proxy (if needed)
                                 |-> exec bwrap --unshare-user --disable-userns ... -- user_cmd

    Args:
        config: SandboxConfig with network_filter enabled
        file_map: Optional file mapping for virtual user files
        build_command_fn: Function to build bwrap command from config
        sandbox_name: Optional sandbox name for overlay info
        overlay_dirs: Optional list of overlay directories

    Returns:
        Exit code from the sandboxed process
    """
    import sys

    nf = config.network_filter

    # Validate all required tools are available
    iptables_path, ip6tables_path, is_multicall = validate_filtering_requirements(nf)

    # Build bwrap command (this is what wrapper.sh will exec)
    bwrap_cmd = build_command_fn(config, file_map)

    # Create wrapper script in temp directory
    import tempfile
    tmp_dir = tempfile.mkdtemp(prefix="bui-net-")
    tmp_path = Path(tmp_dir)

    # Prepare bwrap command (removes --unshare-net, adds bind mounts)
    bwrap_cmd = prepare_bwrap_command(bwrap_cmd, tmp_dir)

    # Get seccomp filter path if present in file_map
    seccomp_filter_path = file_map.get("/seccomp.bpf") if file_map else None

    # Create wrapper script that does iptables setup then execs bwrap
    try:
        wrapper_script_path = create_wrapper_script(
            nf, bwrap_cmd, iptables_path, ip6tables_path, is_multicall, tmp_path,
            seccomp_filter_path=seccomp_filter_path,
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

    # Print header
    from commandoutput import print_execution_header
    print_execution_header(
        bwrap_cmd,
        network_filter=nf,
        sandbox_name=sandbox_name,
        overlay_dirs=overlay_dirs,
    )

    # Build pasta command: pasta [args] -- /bin/sh wrapper.sh
    # We use /bin/sh to execute the script rather than directly because
    # SELinux prevents pasta from executing scripts directly in some contexts
    pasta_args = generate_pasta_args(nf)
    full_cmd = pasta_args + ["--", "/bin/sh", str(wrapper_script_path)]

    # Use pty to run pasta - this prevents terminal corruption when bwrap
    # --new-session receives SIGINT (a known bwrap issue #369)
    sys.stdout.flush()
    sys.stderr.flush()
    return _run_with_pty(full_cmd)


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

    # Create temp directory for pcap file (mkdtemp creates with 0o700)
    tmp_dir = tempfile.mkdtemp(prefix="bui-audit-")
    tmp_path = Path(tmp_dir)

    pcap_path = nf.audit.pcap_path or (tmp_path / "audit.pcap")

    # Build bwrap command
    cmd = build_command_fn(config, file_map)

    # Remove --unshare-net since pasta provides the network namespace
    cmd = [arg for arg in cmd if arg != "--unshare-net"]

    # Handle seccomp filter - need to open FD before subprocess.run
    from command_execution import prepare_seccomp_fd
    cmd, seccomp_fd = prepare_seccomp_fd(cmd, file_map)

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
    # pass_fds ensures seccomp FD is inherited by subprocess
    try:
        pass_fds = (seccomp_fd,) if seccomp_fd is not None else ()
        result = subprocess.run(full_cmd, pass_fds=pass_fds)
        exit_code = result.returncode
    except KeyboardInterrupt:
        print("\nInterrupted by user")
        exit_code = 130
    except FileNotFoundError as e:
        print(f"Error: Command not found: {e}", file=sys.stderr)
        exit_code = 127
    except OSError as e:
        print(f"Error: Failed to run command: {e}", file=sys.stderr)
        exit_code = 1
    finally:
        # Close seccomp FD in parent
        if seccomp_fd is not None:
            try:
                import os
                os.close(seccomp_fd)
            except OSError:
                pass

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
