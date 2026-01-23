"""pasta execution functions for sandbox network setup."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from model.network_filter import NetworkFilter
    from model.sandbox_config import SandboxConfig

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

    # Create wrapper script that does iptables setup then execs bwrap
    try:
        wrapper_script_path = create_wrapper_script(
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


def _run_with_pty(cmd: list[str]) -> int:
    """Run command in a pty with proper cleanup of orphaned processes.

    This handles the case where pasta exits but bwrap gets orphaned to init,
    which would otherwise leave pty.spawn() hanging.
    """
    import io
    import os
    import pty
    import select
    import signal
    import sys
    import termios
    import time
    import tty

    pid, fd = pty.fork()

    if pid == 0:
        # Child - exec the command
        os.execvp(cmd[0], cmd)
        sys.exit(1)  # Never reached

    def cleanup_child() -> int:
        """Terminate and reap the child process, returning exit code."""
        # Check if child already exited
        try:
            result = os.waitpid(pid, os.WNOHANG)
            if result[0] != 0:
                status = result[1]
                if os.WIFEXITED(status):
                    return os.WEXITSTATUS(status)
                return 1
        except ChildProcessError:
            return 0

        # Send SIGTERM to the process group
        try:
            os.killpg(pid, signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            # Process already gone or we can't signal it
            pass

        # Wait up to 2 seconds for termination
        for _ in range(20):
            time.sleep(0.1)
            try:
                result = os.waitpid(pid, os.WNOHANG)
                if result[0] != 0:
                    status = result[1]
                    if os.WIFEXITED(status):
                        return os.WEXITSTATUS(status)
                    return 1
            except ChildProcessError:
                return 0

        # Still running - send SIGKILL
        try:
            os.killpg(pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass

        # Reap with blocking wait
        try:
            _, status = os.waitpid(pid, 0)
            if os.WIFEXITED(status):
                return os.WEXITSTATUS(status)
            return 1
        except ChildProcessError:
            return 0

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
    except KeyboardInterrupt:
        return cleanup_child()
    finally:
        # Restore terminal settings
        if old_settings is not None and stdin_fd is not None:
            termios.tcsetattr(stdin_fd, termios.TCSADRAIN, old_settings)
        # Close pty fd
        try:
            os.close(fd)
        except OSError:
            pass

    # Reap child and get exit status
    return cleanup_child()


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
