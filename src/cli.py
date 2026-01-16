"""Command-line interface for bui."""

import os
import shlex
import sys
from pathlib import Path

from app import BubblewrapTUI
from installer import check_for_updates, do_install, do_update, show_update_notice
from model import SandboxConfig
from profiles import BUI_PROFILES_DIR, Profile

BUI_VERSION = "0.3.3"

# Global to store update message for display after TUI exits
_update_available: str | None = None


def load_profile(profile_path: str, command: list[str]) -> SandboxConfig:
    """Load a profile from a JSON file."""
    from profiles import ProfileValidationError

    path = Path(profile_path).expanduser().resolve()
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


def show_help() -> None:
    """Print help message and exit."""
    print(__doc__ or "Bubblewrap TUI - A visual interface for configuring bubblewrap sandboxes.")
    print(f"Version: {BUI_VERSION}")
    print("\nUsage:")
    print("  bui -- <command> [args...]            Configure and run a sandboxed command")
    print("  bui --profile <file> -- <command>     Load profile and run command")
    print("  bui --install                         Install bui to ~/.local/bin")
    print("  bui --update                          Download latest version and install")
    print("\nExamples:")
    print("  bui -- /bin/bash")
    print("  bui -- python script.py arg1 arg2")
    print('  bui -- "curl foo.sh | bash"           (pipes and redirects auto-handled)')
    print("  bui --profile ~/bui/dev.json -- code  (load profile for command)")
    sys.exit(0)


def parse_args() -> tuple[list[str], str | None]:
    """Parse command line arguments.

    Returns: (command, profile_path)
    """
    args = sys.argv[1:]

    if not args or "--help" in args or "-h" in args:
        show_help()

    if "--install" in args:
        do_install(BUI_VERSION)
        sys.exit(0)

    if "--update" in args:
        do_update(BUI_VERSION)
        sys.exit(0)

    # Check for --profile flag
    profile_path = None
    if "--profile" in args:
        try:
            profile_idx = args.index("--profile")
            if profile_idx + 1 >= len(args) or args[profile_idx + 1].startswith("-"):
                print("Error: --profile requires a file path", file=sys.stderr)
                sys.exit(1)
            profile_path = args[profile_idx + 1]
            # Remove --profile and its argument from args
            args = args[:profile_idx] + args[profile_idx + 2 :]
        except (IndexError, ValueError):
            pass

    try:
        sep_idx = args.index("--")
        command = args[sep_idx + 1 :]
        if not command:
            print("Error: No command specified after '--'", file=sys.stderr)
            print("Usage: bui -- <command> [args...]", file=sys.stderr)
            sys.exit(1)
    except ValueError:
        command = args

    if needs_shell_wrap(command):
        # Join all args with proper quoting and wrap in shell
        return ["/bin/bash", "-c", shlex.join(command)], profile_path
    return command, profile_path


def main() -> None:
    """Main entry point."""
    global _update_available
    command, profile_path = parse_args()

    # Check for updates in background (non-blocking, cached for 1 day)
    _update_available = check_for_updates(BUI_VERSION)

    # Load profile if specified
    if profile_path:
        config = load_profile(profile_path, command)
        app = BubblewrapTUI(command, version=BUI_VERSION, config=config)
    else:
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
