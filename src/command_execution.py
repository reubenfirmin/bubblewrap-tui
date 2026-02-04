"""Command execution and cleanup for sandboxed processes."""

from __future__ import annotations

import io
import os
import pty
import select
import shutil
import signal
import subprocess
import sys
import termios
import time
import tty
from pathlib import Path
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from model.sandbox_config import SandboxConfig


def _get_descendants(pid: int) -> list[int]:
    """Get all descendant PIDs by traversing /proc.

    Works across session boundaries (unlike process groups).
    Returns children-first order for safe termination.
    """
    descendants = []
    to_visit = [pid]

    while to_visit:
        current = to_visit.pop(0)
        try:
            children_path = Path(f"/proc/{current}/task/{current}/children")
            if children_path.exists():
                children_text = children_path.read_text().strip()
                if children_text:
                    for child_str in children_text.split():
                        try:
                            child_pid = int(child_str)
                            if child_pid not in descendants:
                                descendants.append(child_pid)
                                to_visit.append(child_pid)
                        except ValueError:
                            continue
        except (OSError, PermissionError):
            continue

    descendants.reverse()  # Kill deepest first
    return descendants


def _run_with_pty(cmd: list[str]) -> int:
    """Run command in a pty with proper cleanup of orphaned processes.

    This handles the case where pasta exits but bwrap gets orphaned to init,
    which would otherwise leave pty.spawn() hanging. Also handles --new-session
    terminal issues (bwrap issue #369).
    """
    pid, fd = pty.fork()

    if pid == 0:
        # Child - exec the command
        try:
            os.execvp(cmd[0], cmd)
        except OSError as e:
            # Write to stderr (fd 2) directly since we're in raw mode
            os.write(2, f"Error: Failed to execute {cmd[0]}: {e}\n".encode())
            os._exit(127 if isinstance(e, FileNotFoundError) else 1)

    def cleanup_child() -> int:
        """Terminate and reap the child process and all descendants."""
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

        # Find all descendants before signaling (works across session boundaries)
        descendants = _get_descendants(pid)

        # Send SIGTERM to descendants first (children before parents)
        for desc_pid in descendants:
            try:
                os.kill(desc_pid, signal.SIGTERM)
            except (ProcessLookupError, PermissionError):
                pass

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

        # Still running - SIGKILL descendants first
        for desc_pid in descendants:
            try:
                os.kill(desc_pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass

        # SIGKILL the process group
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
                        # Intercept Ctrl+C (0x03) to handle cleanup ourselves
                        # This prevents pasta from dying before we can find descendants
                        if b'\x03' in data:
                            return cleanup_child()
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


def _fix_overlay_workdir_permissions(path: Path) -> None:
    """Fix permissions on overlayfs workdir before deletion.

    Overlayfs sets workdir permissions to 000 to prevent direct access.
    Since the user owns the directory, we can chmod it to allow deletion.
    """
    for root, dirs, files in os.walk(path, topdown=True):
        for d in dirs:
            dir_path = Path(root) / d
            try:
                current_mode = dir_path.stat().st_mode
                if current_mode & 0o700 != 0o700:
                    os.chmod(dir_path, current_mode | 0o700)
            except OSError:
                pass


def execute_sandbox(
    config: "SandboxConfig",
    file_map: dict[str, str] | None,
    build_command_fn: Callable[["SandboxConfig", dict[str, str] | None], list[str]],
    sandbox_name: str | None,
    overlay_dirs: list[Path],
    ephemeral_sandbox_dir: Path | None,
) -> None:
    """Execute a sandboxed command and handle cleanup.

    Dispatches to the appropriate execution path based on network mode.
    Cleans up ephemeral sandbox directories after execution.

    Args:
        config: SandboxConfig with all sandbox settings
        file_map: Optional file mapping for virtual user files
        build_command_fn: Function to build bwrap command from config
        sandbox_name: Sandbox name for overlay info display
        overlay_dirs: List of overlay directories being used
        ephemeral_sandbox_dir: Directory to clean up after execution (for auto-generated sandboxes)
    """
    from net import execute_with_audit, execute_with_network_filter

    exit_code = 0
    try:
        if config.network_filter.is_audit_mode():
            exit_code = execute_with_audit(
                config,
                file_map,
                build_command_fn,
                sandbox_name if overlay_dirs else None,
                overlay_dirs,
            )
        elif config.network_filter.is_filter_mode():
            exit_code = execute_with_network_filter(
                config,
                file_map,
                build_command_fn,
                sandbox_name if overlay_dirs else None,
                overlay_dirs,
            )
        else:
            exit_code = _execute_direct(
                config, file_map, build_command_fn, sandbox_name, overlay_dirs, ephemeral_sandbox_dir
            )
    finally:
        if ephemeral_sandbox_dir and ephemeral_sandbox_dir.exists():
            _fix_overlay_workdir_permissions(ephemeral_sandbox_dir)
            shutil.rmtree(ephemeral_sandbox_dir, ignore_errors=True)

    sys.exit(exit_code)


def _execute_direct(
    config: "SandboxConfig",
    file_map: dict[str, str] | None,
    build_command_fn: Callable[["SandboxConfig", dict[str, str] | None], list[str]],
    sandbox_name: str | None,
    overlay_dirs: list[Path],
    ephemeral_sandbox_dir: Path | None,
) -> int:
    """Execute directly without pasta.

    Uses PTY to handle --new-session terminal issues (bwrap issue #369).
    This prevents interactive CLI tools from freezing.
    """
    from commandoutput import print_execution_header

    cmd = build_command_fn(config, file_map)
    print_execution_header(
        cmd,
        sandbox_name=sandbox_name if overlay_dirs else None,
        overlay_dirs=overlay_dirs,
    )

    # Use PTY to handle --new-session terminal issues (bwrap #369)
    # This prevents interactive CLI tools from freezing
    sys.stdout.flush()
    sys.stderr.flush()
    return _run_with_pty(cmd)
