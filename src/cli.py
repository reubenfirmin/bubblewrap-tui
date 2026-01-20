"""Command-line interface for bui."""

import argparse
import os
import shlex
import sys
import uuid
from pathlib import Path

from app import BubblewrapTUI
from installer import check_for_updates, do_install, do_update, show_update_notice
from model import BoundDirectory, SandboxConfig
from profiles import BUI_PROFILES_DIR, Profile
from sandbox import (
    BUI_STATE_DIR,
    find_executables,
    install_sandbox_binary,
    list_overlays,
    list_sandboxes,
    uninstall_sandbox,
)

BUI_VERSION = "0.3.5"

# Global to store update message for display after TUI exits
_update_available: str | None = None


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
            "  bui --bind-cwd                        Bind CWD read-write (use with --profile)",
            "",
            "Sandbox Management:",
            "  bui --sandbox <name> --install [--profile <p>]",
            "                                        Create wrapper script in ~/.local/bin",
            "                                        (uses 'untrusted' profile by default)",
            "  bui --sandbox <name> --uninstall      Remove sandbox and wrapper scripts",
            "  bui --list-sandboxes                  List installed sandboxes",
            "  bui --list-overlays                   List overlay directories",
            "",
            "Examples:",
            "  bui -- /bin/bash",
            "  bui -- python script.py arg1 arg2",
            "  bui --profile untrusted --sandbox deno -- 'curl -fsSL https://deno.land/install.sh | sh'",
            "  bui --sandbox deno --install",
            "  bui --list-sandboxes",
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
    parser.add_argument("--bind-cwd", action="store_true", help=argparse.SUPPRESS)

    # Sandbox management
    parser.add_argument("--uninstall", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--list-sandboxes", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--list-overlays", action="store_true", help=argparse.SUPPRESS)

    # Command to run (everything after --)
    parser.add_argument("command", nargs="*", help=argparse.SUPPRESS)

    return parser


def parse_args() -> tuple[list[str], str | None, str | None, bool]:
    """Parse command line arguments.

    Returns: (command, profile_path, sandbox_name, bind_cwd)
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

    # Sandbox management actions (require --sandbox)
    if args.install and args.sandbox:
        profile = args.profile if args.profile else "untrusted"
        install_sandbox_binary(args.sandbox, profile)
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

    return command, args.profile, args.sandbox, args.bind_cwd


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


def main() -> None:
    """Main entry point."""
    global _update_available
    command, profile_path, sandbox_name, bind_cwd = parse_args()

    # Check for updates in background (non-blocking, cached for 1 day)
    _update_available = check_for_updates(BUI_VERSION)

    # If profile specified, run directly without TUI
    if profile_path:
        config = load_profile(profile_path, command)

        # Apply --bind-cwd: add current directory as read-write bound directory
        if bind_cwd:
            cwd = Path(os.getcwd())
            config.bound_dirs.append(BoundDirectory(path=cwd, readonly=False))

        # Apply sandbox isolation to overlays
        overlay_dirs = []
        if config.overlays:
            # Generate UUID if no sandbox name specified
            if sandbox_name is None:
                sandbox_name = str(uuid.uuid4())[:8]
            overlay_dirs = apply_sandbox_to_overlays(config, sandbox_name)

        cmd = config.build_command()
        print("=" * 60)
        print("Executing:")
        print(" ".join(cmd))
        if overlay_dirs:
            print(f"\nSandbox: {sandbox_name}")
            print("Overlay writes will go to:")
            for d in overlay_dirs:
                print(f"  {d}/")
        print("=" * 60 + "\n")
        os.execvp("bwrap", cmd)

    # Otherwise show TUI for configuration
    app = BubblewrapTUI(command, version=BUI_VERSION)
    app.run()

    # Show update notice after TUI exits
    if _update_available:
        show_update_notice(BUI_VERSION, _update_available)

    if app._execute_command:
        cmd = app.config.build_command()
        print("=" * 60)
        print("Executing:")
        print(" ".join(cmd))
        print("=" * 60 + "\n")

        os.execvp("bwrap", cmd)
    else:
        print("Cancelled.")
        sys.exit(0)


if __name__ == "__main__":
    main()
