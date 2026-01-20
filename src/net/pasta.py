"""pasta network namespace wrapper.

pasta (part of passt) provides user-mode networking for sandboxes.
It creates a network namespace and provides connectivity without
requiring special privileges.

In spawn mode, pasta creates a new user+network namespace and runs
the given command inside. This is simpler than slirp4netns and
requires no CAP_SYS_ADMIN.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from model.network_filter import NetworkFilter

from net.utils import detect_distro


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


def generate_pasta_args(nf: NetworkFilter) -> list[str]:
    """Generate pasta command arguments for spawn mode.

    In spawn mode, pasta creates a new user+network namespace and runs
    the given command inside. This is simpler than attach mode and
    doesn't require special privileges.

    Args:
        nf: NetworkFilter configuration

    Returns:
        Command arguments for pasta (without the command to run).
    """
    args = [
        "pasta",
        "--config-net",  # Auto-configure networking
        "--quiet",  # Suppress output
    ]

    # Forward localhost ports (container → host)
    # -T forwards TCP ports from sandbox to host localhost
    for port in nf.localhost_access.ports:
        args.extend(["-T", str(port)])

    # The "--" separator and command will be added by caller
    return args


def execute_with_pasta(
    config: "SandboxConfig",
    fd_map: dict[str, int] | None,
    build_command_fn: callable,
    sandbox_name: str | None = None,
    overlay_dirs: list[str] | None = None,
) -> None:
    """Execute bwrap with network filtering via pasta spawn mode.

    pasta creates a new user+network namespace and runs bwrap inside.
    This is much simpler than the attach mode and requires no special privileges.

    Architecture:
        pasta --config-net -- bwrap [args] -- init_script

    The init script applies iptables rules then runs the user command.

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

    # Create temp directory for scripts
    tmp_dir = tempfile.mkdtemp(prefix="bui-net-")
    tmp_path = Path(tmp_dir)
    init_script_path = tmp_path / "init.sh"

    # Generate iptables init script content
    iptables_script = generate_init_script(nf, iptables_path, ip6tables_path, is_multicall)

    # Build the user command as a shell-safe string
    user_cmd = " ".join(shlex.quote(arg) for arg in config.command)

    # Create the init script that applies iptables rules then runs user command
    # pasta --config-net already sets up the network interface before running bwrap
    init_wrapper = f'''#!/bin/sh
set -e

# Set up iptables rules
{iptables_script}

# Run the user command
exec {user_cmd}
'''

    init_script_path.write_text(init_wrapper)
    init_script_path.chmod(0o755)

    # Build bwrap command - pasta provides network namespace, so remove --unshare-net
    original_command = config.command
    config.command = [str(init_script_path)]

    cmd = build_command_fn(config, fd_map)
    config.command = original_command

    # Remove --unshare-net since pasta provides the network namespace
    try:
        idx = cmd.index("--unshare-net")
        cmd.pop(idx)
    except ValueError:
        pass

    # Find the "--" separator and insert bind mount BEFORE it
    try:
        separator_idx = cmd.index("--")
        cmd.insert(separator_idx, "--bind")
        cmd.insert(separator_idx + 1, tmp_dir)
        cmd.insert(separator_idx + 2, tmp_dir)
    except ValueError:
        cmd.extend(["--bind", tmp_dir, tmp_dir])

    # Remove CAP_NET_ADMIN from drop_caps if present, and add it explicitly
    try:
        cap_drop_idx = cmd.index("--cap-drop")
        while cap_drop_idx < len(cmd) - 1:
            if cmd[cap_drop_idx] == "--cap-drop" and cmd[cap_drop_idx + 1] == "CAP_NET_ADMIN":
                cmd.pop(cap_drop_idx)
                cmd.pop(cap_drop_idx)
                break
            cap_drop_idx = cmd.index("--cap-drop", cap_drop_idx + 1)
    except ValueError:
        pass

    # Add CAP_NET_ADMIN capability for iptables
    separator_idx = cmd.index("--")
    cmd.insert(separator_idx, "--cap-add")
    cmd.insert(separator_idx + 1, "CAP_NET_ADMIN")

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
