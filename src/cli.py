"""Command-line interface for bui."""

import argparse
import os
import shlex
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from model import SandboxConfig

from app import BubblewrapTUI
from commandoutput import print_execution_header
from installer import check_for_updates, do_install, do_update, show_update_notice
from model import BoundDirectory, SandboxConfig
from net import check_pasta, execute_with_audit, execute_with_network_filter, get_install_instructions
from profiles import BUI_PROFILES_DIR, Profile
from sandbox import (
    BUI_STATE_DIR,
    clean_temp_files,
    find_executables,
    install_sandbox_binary,
    list_overlays,
    list_profiles,
    list_sandboxes,
    register_sandbox,
    uninstall_sandbox,
)

BUI_VERSION = "0.5.0"

# Global to store update message for display after TUI exits
_update_available: str | None = None


@dataclass
class ParsedArgs:
    """Parsed command-line arguments."""

    command: list[str]
    profile_path: str | None
    sandbox_name: str | None
    bind_cwd: bool
    bind_paths: list[Path]
    bind_env: list[str]


def print_error_box(title: str, *lines: str) -> None:
    """Print a formatted error box to stderr.

    Args:
        title: The error title (will be prefixed with "Error: ")
        *lines: Additional lines to print in the box
    """
    print("=" * 60, file=sys.stderr)
    print(f"Error: {title}", file=sys.stderr)
    print("", file=sys.stderr)
    for line in lines:
        print(line, file=sys.stderr)
    print("=" * 60, file=sys.stderr)


def load_profile(profile_name: str, command: list[str]) -> SandboxConfig:
    """Load a profile from the profiles directory.

    Args:
        profile_name: Profile name (without .json) or full path
        command: Command to run in sandbox
    """
    from profiles import ProfileValidationError

    # If it's a simple name (no path separators), look in the default profiles dir
    if "/" not in profile_name and "\\" not in profile_name:
        # Add .json extension if not present
        if not profile_name.endswith(".json"):
            profile_name = f"{profile_name}.json"
        path = BUI_PROFILES_DIR / profile_name
    else:
        # Explicit path provided
        path = Path(profile_name).expanduser().resolve()

    if not path.exists():
        print(f"Error: Profile not found: {path}", file=sys.stderr)
        sys.exit(1)

    try:
        profile = Profile(path)
        config, warnings = profile.load(command)
        # Print any warnings
        for warning in warnings:
            print(f"Warning: {warning}", file=sys.stderr)
        return config
    except ProfileValidationError as e:
        print(f"Profile validation error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error loading profile: {e}", file=sys.stderr)
        sys.exit(1)


def needs_shell_wrap(command: list[str]) -> bool:
    """Check if command needs to be wrapped in a shell.

    Checks all arguments for shell metacharacters, not just single-arg commands.
    This handles cases like: /bin/bash -c "cmd | cmd"
    """
    shell_chars = ["|", "&&", "||", ";", ">", "<", "$(", "`"]
    # Check all arguments for shell metacharacters
    for arg in command:
        if any(c in arg for c in shell_chars):
            return True
    return False


class BuiHelpFormatter(argparse.RawDescriptionHelpFormatter):
    """Custom formatter that shows our structured help."""

    def format_help(self) -> str:
        lines = [
            "Bubblewrap TUI - A visual interface for configuring bubblewrap sandboxes.",
            f"Version: {BUI_VERSION}",
            "",
            "Core:",
            "  bui -- <command> [args...]            Configure and run a sandboxed command",
            "",
            "Bui Install/Update:",
            "  bui --install                         Install bui to ~/.local/bin",
            "  bui --update                          Download latest version and install",
            "",
            "Profile Options:",
            "  bui --profile <name> -- <command>     Load profile and run command",
            "  bui --sandbox <name>                  Name for overlay storage (use with --profile)",
            "  bui --bind <path>                     Bind path read-only (repeatable)",
            "  bui --bind-cwd                        Bind CWD read-write",
            "  bui --bind-env <VAR=VALUE>            Set env var in sandbox (repeatable)",
            "  bui --list-profiles                   List available profiles",
            "",
            "Sandbox Management:",
            "  bui --sandbox <name> --install [--profile <p>]",
            "                                        Create wrapper script in ~/.local/bin",
            "                                        (uses 'untrusted' profile by default)",
            "  bui --sandbox <name> --uninstall      Remove sandbox and wrapper scripts",
            "  bui --list-sandboxes                  List installed sandboxes",
            "  bui --list-overlays                   List overlay directories",
            "  bui --clean                           Remove temporary network filter files",
            "",
            "Examples:",
            "",
            "  # Launch TUI to configure a sandbox interactively",
            "  bui -- /bin/bash",
            "  bui -- python script.py arg1 arg2",
            "",
            "  # Install deno in an isolated sandbox (curl|bash pattern)",
            "  bui --profile untrusted --sandbox deno -- 'curl -fsSL https://deno.land/install.sh | sh'",
            "  bui --sandbox deno --install",
            "",
            "  # Install claude-code - requires binding npm dir and setting NPM_CONFIG_PREFIX",
            "  # (Potentially cleaner: fork 'untrusted' in TUI with npm dir + NPM_CONFIG_PREFIX)",
            "  bui --profile untrusted --sandbox claude --bind $(dirname $(which npm)) \\",
            "       --bind-env NPM_CONFIG_PREFIX=/home/sandbox/.npm-global \\",
            "       -- npm install -g @anthropic-ai/claude-code",
            "",
            "Built-in Profiles:",
            "  untrusted    Safe sandbox for running untrusted code (curl|bash scripts)",
            "               - Read-only system paths, isolated namespaces",
            "               - Home directory overlay (isolated per --sandbox or UUID)",
            "               - Network enabled for downloads",
            "",
            "  Example: bui --profile untrusted --sandbox myapp -- bash",
        ]
        return "\n".join(lines) + "\n"


def create_parser() -> argparse.ArgumentParser:
    """Create argument parser for bui CLI."""
    parser = argparse.ArgumentParser(
        prog="bui",
        formatter_class=BuiHelpFormatter,
        add_help=True,
    )

    # Bui install/update (mutually exclusive standalone actions)
    parser.add_argument("--install", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--update", action="store_true", help=argparse.SUPPRESS)

    # Profile options
    parser.add_argument("--profile", metavar="NAME", help=argparse.SUPPRESS)
    parser.add_argument("--sandbox", metavar="NAME", help=argparse.SUPPRESS)
    parser.add_argument("--bind", metavar="PATH", action="append", default=[], help=argparse.SUPPRESS)
    parser.add_argument("--bind-cwd", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--bind-env", metavar="VAR=VALUE", action="append", default=[], help=argparse.SUPPRESS)

    # Sandbox management
    parser.add_argument("--uninstall", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--list-sandboxes", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--list-overlays", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--list-profiles", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--clean", action="store_true", help=argparse.SUPPRESS)

    # Command to run (everything after --)
    parser.add_argument("command", nargs="*", help=argparse.SUPPRESS)

    return parser


def parse_args() -> ParsedArgs:
    """Parse command line arguments.

    Returns:
        ParsedArgs with command, profile, sandbox, and bind options.
    """
    parser = create_parser()

    # Handle -- separator: argparse treats it specially, but we want to capture
    # everything after -- as the command, including things that look like flags
    argv = sys.argv[1:]
    if "--" in argv:
        sep_idx = argv.index("--")
        bui_args = argv[:sep_idx]
        command_args = argv[sep_idx + 1 :]
    else:
        bui_args = argv
        command_args = []

    # Parse bui's own arguments
    args = parser.parse_args(bui_args)

    # Handle standalone actions first (these exit immediately)

    # bui --install (self-install, only when --sandbox is NOT present)
    if args.install and not args.sandbox:
        do_install(BUI_VERSION)
        sys.exit(0)

    if args.update:
        do_update(BUI_VERSION)
        sys.exit(0)

    if args.list_sandboxes:
        list_sandboxes()
        sys.exit(0)

    if args.list_overlays:
        list_overlays()
        sys.exit(0)

    if args.list_profiles:
        list_profiles()
        sys.exit(0)

    if args.clean:
        clean_temp_files()
        sys.exit(0)

    # Sandbox management actions (require --sandbox)
    if args.install and args.sandbox:
        profile = args.profile if args.profile else "untrusted"
        bind_paths = [str(Path(p).expanduser().resolve()) for p in args.bind] if args.bind else None
        bind_env = args.bind_env if args.bind_env else None
        install_sandbox_binary(args.sandbox, profile, bind_paths, bind_env)
        sys.exit(0)

    if args.uninstall:
        if not args.sandbox:
            print("Error: --uninstall requires --sandbox <name>", file=sys.stderr)
            sys.exit(1)
        uninstall_sandbox(args.sandbox)
        sys.exit(0)

    # Build the command to run
    # Command can come from after -- or from positional args
    command = command_args if command_args else args.command

    if not command:
        # No command specified - show help
        parser.print_help()
        sys.exit(0)

    # Wrap in shell if needed
    if needs_shell_wrap(command):
        if len(command) == 1:
            # Single string with shell metacharacters - pass directly to -c
            command = ["/bin/bash", "-c", command[0]]
        else:
            # Multiple arguments with shell metacharacters - join them
            command = ["/bin/bash", "-c", shlex.join(command)]

    # Resolve bind paths
    bind_paths = [Path(p).expanduser().resolve() for p in args.bind]

    return ParsedArgs(
        command=command,
        profile_path=args.profile,
        sandbox_name=args.sandbox,
        bind_cwd=args.bind_cwd,
        bind_paths=bind_paths,
        bind_env=args.bind_env,
    )


def cleanup_fds(fd_map: dict[str, int]) -> None:
    """Close all file descriptors in the map.

    Used to clean up FDs on error paths before exit.
    """
    for fd in fd_map.values():
        try:
            os.close(fd)
        except OSError:
            pass


def setup_virtual_user_fds(config: SandboxConfig) -> dict[str, int]:
    """Set up file descriptors for virtual user files.

    Creates pipes and writes passwd/group content to them. The read ends
    are kept open for bwrap to read from.

    Args:
        config: The sandbox configuration

    Returns:
        Mapping of dest_path -> FD number for use with --ro-bind-data
    """
    virtual_user_data = config.get_virtual_user_data()
    if not virtual_user_data:
        return {}

    fd_map = {}
    for content, dest_path in virtual_user_data:
        # Create a pipe
        read_fd, write_fd = os.pipe()

        # Write content to the pipe
        os.write(write_fd, content.encode())
        os.close(write_fd)

        # Make the read FD inheritable (Python 3.4+ creates non-inheritable FDs by default)
        os.set_inheritable(read_fd, True)

        # Keep the read FD open for bwrap
        fd_map[dest_path] = read_fd

    return fd_map


def execute_bwrap(config: SandboxConfig) -> None:
    """Execute bwrap with virtual user support.

    Sets up FDs for virtual user files if needed, then execs bwrap.
    """
    fd_map = setup_virtual_user_fds(config)
    cmd = config.build_command(fd_map if fd_map else None)
    os.execvp("bwrap", cmd)


def apply_sandbox_to_overlays(config: SandboxConfig, sandbox_name: str) -> list[Path]:
    """Apply sandbox name to overlay write directories.

    Returns list of overlay write directories that may be written to.
    """
    overlay_dirs = []
    for overlay in config.overlays:
        if overlay.write_dir:
            # Replace the base write_dir with sandbox-specific path
            base_dir = BUI_STATE_DIR / "overlays" / sandbox_name
            base_dir.mkdir(parents=True, exist_ok=True)
            overlay.write_dir = str(base_dir)
            overlay_dirs.append(base_dir)

            # Ensure the derived work_dir also exists
            # (get_work_dir() computes parent / ".overlay-work")
            work_dir = Path(overlay.get_work_dir())
            work_dir.mkdir(parents=True, exist_ok=True)
    return overlay_dirs


def validate_network_filter(config: SandboxConfig) -> bool:
    """Validate network filtering requirements.

    Returns True if network filtering can proceed, False if there's an error.
    """
    nf = config.network_filter
    if not nf.requires_pasta():
        return True

    if not check_pasta():
        print_error_box(
            "Network filtering requires pasta",
            f"Install with: {get_install_instructions()}",
            "",
            "Or disable network filtering in the profile.",
        )
        return False

    return True


def _build_bwrap_command(config: SandboxConfig, fd_map: dict[str, int] | None) -> list[str]:
    """Helper to build bwrap command from config."""
    return config.build_command(fd_map)


def main() -> None:
    """Main entry point."""
    global _update_available
    args = parse_args()

    # Check for updates in background (non-blocking, cached for 1 day)
    _update_available = check_for_updates(BUI_VERSION)

    # If profile specified, run directly without TUI
    if args.profile_path:
        config = load_profile(args.profile_path, args.command)

        # Apply --bind: add paths as read-only bound directories
        for path in args.bind_paths:
            config.bound_dirs.append(BoundDirectory(path=path, readonly=True))

        # Apply --bind-cwd: add current directory as read-write bound directory
        if args.bind_cwd:
            cwd = Path(os.getcwd())
            config.bound_dirs.append(BoundDirectory(path=cwd, readonly=False))

        # Apply --bind-env: set environment variables in sandbox
        for env_spec in args.bind_env:
            if "=" in env_spec:
                var, value = env_spec.split("=", 1)
                config.environment.custom_env_vars[var] = value

        # Apply sandbox isolation to overlays
        overlay_dirs = []
        sandbox_name = args.sandbox_name
        user_provided_sandbox = sandbox_name is not None
        if config.overlays:
            # Generate UUID if no sandbox name specified
            if sandbox_name is None:
                sandbox_name = str(uuid.uuid4())[:8]
            overlay_dirs = apply_sandbox_to_overlays(config, sandbox_name)

        # Register sandbox metadata (so --install can pick up binds later)
        if user_provided_sandbox:
            bind_paths_str = [str(p) for p in args.bind_paths] if args.bind_paths else None
            register_sandbox(sandbox_name, args.profile_path, bind_paths_str, args.bind_env)

        # Validate network filtering requirements
        if not validate_network_filter(config):
            sys.exit(1)

        fd_map = setup_virtual_user_fds(config)

        # Dispatch based on network mode
        if config.network_filter.is_audit_mode():
            # Network auditing - capture traffic and show summary after exit
            execute_with_audit(
                config,
                fd_map if fd_map else None,
                _build_bwrap_command,
                sandbox_name if overlay_dirs else None,
                overlay_dirs,
            )
        elif config.network_filter.is_filter_mode():
            # Network filtering - apply iptables rules
            execute_with_network_filter(
                config,
                fd_map if fd_map else None,
                _build_bwrap_command,
                sandbox_name if overlay_dirs else None,
                overlay_dirs,
            )
        else:
            # Normal execution without pasta
            cmd = config.build_command(fd_map if fd_map else None)
            print_execution_header(
                cmd,
                sandbox_name=sandbox_name if overlay_dirs else None,
                overlay_dirs=overlay_dirs,
            )
            os.execvp("bwrap", cmd)

    # Otherwise show TUI for configuration
    app = BubblewrapTUI(args.command, version=BUI_VERSION)
    app.run()

    # Show update notice after TUI exits
    if _update_available:
        show_update_notice(BUI_VERSION, _update_available)

    if app._execute_command:
        # Validate network filtering requirements
        if not validate_network_filter(app.config):
            sys.exit(1)

        fd_map = setup_virtual_user_fds(app.config)

        # Dispatch based on network mode
        if app.config.network_filter.is_audit_mode():
            # Network auditing - capture traffic and show summary after exit
            execute_with_audit(
                app.config,
                fd_map if fd_map else None,
                _build_bwrap_command,
            )
        elif app.config.network_filter.is_filter_mode():
            # Network filtering - apply iptables rules
            execute_with_network_filter(
                app.config,
                fd_map if fd_map else None,
                _build_bwrap_command,
            )
        else:
            # Normal execution without pasta
            cmd = app.config.build_command(fd_map if fd_map else None)
            print_execution_header(cmd)
            os.execvp("bwrap", cmd)
    else:
        print("Cancelled.")
        sys.exit(0)


if __name__ == "__main__":
    main()
