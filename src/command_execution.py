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


def execute_sandbox(
    config: "SandboxConfig",
    file_map: dict[str, str] | None,
    build_command_fn: Callable[["SandboxConfig", dict[str, str] | None], list[str]],
    sandbox_name: str | None,
    overlay_dirs: list[Path],
    ephemeral_sandbox_dir: Path | None,
    use_standalone_seccomp: bool,
) -> None:
    """Execute a sandboxed command and handle cleanup.

    Dispatches to the appropriate execution path based on network mode and seccomp
    settings. Cleans up ephemeral sandbox directories after execution.

    Args:
        config: SandboxConfig with all sandbox settings
        file_map: Optional file mapping for virtual user files
        build_command_fn: Function to build bwrap command from config
        sandbox_name: Sandbox name for overlay info display
        overlay_dirs: List of overlay directories being used
        ephemeral_sandbox_dir: Directory to clean up after execution (for auto-generated sandboxes)
        use_standalone_seccomp: Whether to use seccomp-only mode
    """
    from commandoutput import print_execution_header
    from net import execute_with_audit, execute_with_network_filter
    from seccomp import create_seccomp_init_script

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
        elif use_standalone_seccomp:
            exit_code = _execute_with_seccomp(
                config, file_map, build_command_fn, sandbox_name, overlay_dirs, ephemeral_sandbox_dir
            )
        else:
            exit_code = _execute_direct(
                config, file_map, build_command_fn, sandbox_name, overlay_dirs, ephemeral_sandbox_dir
            )
    finally:
        if ephemeral_sandbox_dir and ephemeral_sandbox_dir.exists():
            shutil.rmtree(ephemeral_sandbox_dir, ignore_errors=True)

    sys.exit(exit_code)


def _execute_with_seccomp(
    config: "SandboxConfig",
    file_map: dict[str, str] | None,
    build_command_fn: Callable[["SandboxConfig", dict[str, str] | None], list[str]],
    sandbox_name: str | None,
    overlay_dirs: list[Path],
    ephemeral_sandbox_dir: Path | None,
) -> int:
    """Execute with seccomp-only mode (no network filtering)."""
    from commandoutput import print_execution_header
    from seccomp import create_seccomp_init_script

    init_script_path = create_seccomp_init_script(config.command)
    tmp_dir = str(init_script_path.parent)
    original_command = config.command
    config.command = [str(init_script_path)]
    cmd = build_command_fn(config, file_map)
    config.command = original_command

    # Bind mount the temp directory so the script is accessible inside sandbox
    try:
        separator_idx = cmd.index("--")
        cmd.insert(separator_idx, "--bind")
        cmd.insert(separator_idx + 1, tmp_dir)
        cmd.insert(separator_idx + 2, tmp_dir)
    except ValueError:
        cmd.extend(["--bind", tmp_dir, tmp_dir])

    print_execution_header(
        cmd,
        sandbox_name=sandbox_name if overlay_dirs else None,
        overlay_dirs=overlay_dirs,
        seccomp_enabled=True,
    )

    if ephemeral_sandbox_dir:
        result = subprocess.run(cmd)
        return result.returncode
    else:
        os.execvp("bwrap", cmd)
        return 0  # Never reached


def _execute_direct(
    config: "SandboxConfig",
    file_map: dict[str, str] | None,
    build_command_fn: Callable[["SandboxConfig", dict[str, str] | None], list[str]],
    sandbox_name: str | None,
    overlay_dirs: list[Path],
    ephemeral_sandbox_dir: Path | None,
) -> int:
    """Execute directly without pasta or seccomp."""
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
