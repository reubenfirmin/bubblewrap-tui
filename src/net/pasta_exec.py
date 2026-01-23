"""pasta execution functions for sandbox network setup."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from model.network_filter import NetworkFilter
    from model.sandbox_config import SandboxConfig

from net.filtering import validate_filtering_requirements
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

    # Create wrapper script in a location pasta can execute from
    # SELinux on Fedora prevents pasta from executing scripts in dirs with
    # cache_home_t or data_home_t contexts. Only user_home_t works.
    # ~/.bui-run/ inherits user_home_t from $HOME
    import tempfile
    run_dir = Path.home() / ".bui-run"
    run_dir.mkdir(parents=True, exist_ok=True)
    tmp_dir = tempfile.mkdtemp(prefix="net-", dir=run_dir)
    tmp_path = Path(tmp_dir)

    # Prepare bwrap command (removes --unshare-net, adds bind mounts)
    bwrap_cmd = prepare_bwrap_command(bwrap_cmd, tmp_dir)

    # Create wrapper script that does iptables setup then execs bwrap
    try:
        wrapper_script_path = _create_wrapper_with_tmp(
            nf, bwrap_cmd, iptables_path, ip6tables_path, is_multicall, tmp_path
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


def _create_wrapper_with_tmp(
    nf: "NetworkFilter",
    bwrap_cmd: list[str],
    iptables_path: str,
    ip6tables_path: str | None,
    is_multicall: bool,
    tmp_path: Path,
) -> Path:
    """Create wrapper script in the given tmp directory.

    This is a helper that creates the wrapper script components in a pre-existing
    temp directory (which is needed because prepare_bwrap_command needs to know
    the tmp_dir before we create the wrapper).
    """
    import shlex

    from net.dns_proxy import generate_dns_proxy_script, get_dns_proxy_init_commands, needs_dns_proxy
    from net.iptables import generate_init_script

    wrapper_script_path = tmp_path / "wrapper.sh"

    iptables_script = generate_init_script(nf, iptables_path, ip6tables_path, is_multicall)

    # Check if DNS proxy is needed for hostname filtering
    dns_proxy_setup = ""
    if needs_dns_proxy(nf.hostname_filter):
        dns_proxy_script_path = tmp_path / "dns_proxy.py"
        dns_proxy_script = generate_dns_proxy_script(nf.hostname_filter)
        dns_proxy_script_path.write_text(dns_proxy_script)
        dns_proxy_script_path.chmod(0o755)
        dns_proxy_setup = get_dns_proxy_init_commands(str(dns_proxy_script_path))

        # Write resolv.conf to temp dir - will be ro-bind mounted by bwrap
        resolv_conf_path = tmp_path / "resolv.conf"
        resolv_conf_path.write_text("# DNS handled by bubblewrap-tui DNS proxy\nnameserver 127.0.0.1\n")
        resolv_conf_path.chmod(0o444)

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

    wrapper_script_path.write_text(wrapper_script)
    wrapper_script_path.chmod(0o755)

    return wrapper_script_path


def _run_with_pty(cmd: list[str]) -> int:
    """Run command in a pty with proper cleanup of orphaned processes.

    This handles the case where pasta exits but bwrap gets orphaned to init,
    which would otherwise leave pty.spawn() hanging.
    """
    import io
    import os
    import pty
    import select
    import sys
    import termios
    import tty

    pid, fd = pty.fork()

    if pid == 0:
        # Child - exec the command
        os.execvp(cmd[0], cmd)
        sys.exit(1)  # Never reached

    # Parent - copy data between pty and stdin/stdout
    old_settings = None
    try:
        stdin_fd = sys.stdin.fileno()
        if os.isatty(stdin_fd):
            old_settings = termios.tcgetattr(stdin_fd)
            tty.setraw(stdin_fd)
    except (io.UnsupportedOperation, OSError):
        stdin_fd = None

    try:
        while True:
            # Check if child is still alive
            result = os.waitpid(pid, os.WNOHANG)
            if result[0] != 0:
                # Child exited
                status = result[1]
                if os.WIFEXITED(status):
                    return os.WEXITSTATUS(status)
                return 1

            # Wait for data on stdin or pty
            try:
                read_fds = [fd] if stdin_fd is None else [stdin_fd, fd]
                r, _, _ = select.select(read_fds, [], [], 0.1)
            except (select.error, ValueError):
                break

            if stdin_fd is not None and stdin_fd in r:
                try:
                    data = os.read(stdin_fd, 1024)
                    if data:
                        os.write(fd, data)
                except OSError:
                    break

            if fd in r:
                try:
                    data = os.read(fd, 1024)
                    if data:
                        try:
                            os.write(sys.stdout.fileno(), data)
                        except (io.UnsupportedOperation, OSError):
                            sys.stdout.buffer.write(data)
                            sys.stdout.buffer.flush()
                    else:
                        # EOF on pty - child closed it
                        break
                except OSError:
                    break
    finally:
        # Restore terminal settings
        if old_settings is not None and stdin_fd is not None:
            termios.tcsetattr(stdin_fd, termios.TCSADRAIN, old_settings)

    # Reap child and get exit status
    try:
        _, status = os.waitpid(pid, 0)
        if os.WIFEXITED(status):
            return os.WEXITSTATUS(status)
        return 1
    except ChildProcessError:
        return 0


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
    # Use ~/.bui-run for SELinux compatibility (user_home_t context)
    run_dir = Path.home() / ".bui-run"
    run_dir.mkdir(parents=True, exist_ok=True)
    tmp_dir = tempfile.mkdtemp(prefix="audit-", dir=run_dir)
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
