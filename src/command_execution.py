"""Command execution and cleanup for sandboxed processes."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from model.sandbox_config import SandboxConfig


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
    """Execute directly without pasta."""
    from commandoutput import print_execution_header

    cmd = build_command_fn(config, file_map)
    print_execution_header(
        cmd,
        sandbox_name=sandbox_name if overlay_dirs else None,
        overlay_dirs=overlay_dirs,
    )

    if ephemeral_sandbox_dir:
        result = subprocess.run(cmd)
        return result.returncode
    else:
        os.execvp("bwrap", cmd)
        return 0  # Never reached
