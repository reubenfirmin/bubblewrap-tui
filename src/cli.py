"""Command-line interface for bui."""

import os
import shlex
import sys
import uuid
from pathlib import Path

from app import BubblewrapTUI
from installer import check_for_updates, do_install, do_update, show_update_notice
from model import BoundDirectory, SandboxConfig
from profiles import BUI_PROFILES_DIR, Profile

BUI_VERSION = "0.3.5"

# Base directory for overlay storage
BUI_STATE_DIR = Path.home() / ".local" / "state" / "bui"

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


def show_help() -> None:
    """Print help message and exit."""
    print(__doc__ or "Bubblewrap TUI - A visual interface for configuring bubblewrap sandboxes.")
    print(f"Version: {BUI_VERSION}")
    print("\nUsage:")
    print("  bui -- <command> [args...]            Configure and run a sandboxed command")
    print("  bui --profile <name> -- <command>     Load profile and run command")
    print("  bui --sandbox <name>                  Name for overlay storage (use with --profile)")
    print("  bui --bind-cwd                        Bind CWD read-write (use with --profile)")
    print("  bui --sandbox <name> --generate       Generate shell alias for sandbox binary")
    print("  bui --install                         Install bui to ~/.local/bin")
    print("  bui --update                          Download latest version and install")
    print("\nExamples:")
    print("  bui -- /bin/bash")
    print("  bui -- python script.py arg1 arg2")
    print('  bui -- "curl foo.sh | bash"           (pipes and redirects auto-handled)')
    print("  bui --profile myprofile -- code       (load from ~/.config/bui/profiles/)")
    print("  bui --profile untrusted --sandbox deno -- ./install.sh")
    print("                                        (writes go to ~/.local/state/bui/overlays/deno/)")
    print("  bui --sandbox deno --generate         (generate alias for installed binary)")
    print("\nBuilt-in Profiles:")
    print("  untrusted    Safe sandbox for running untrusted code (curl|bash scripts)")
    print("               - Read-only system paths, isolated namespaces")
    print("               - Home directory overlay (isolated per --sandbox or UUID)")
    print("               - Network enabled for downloads")
    print("\n  Example: bui --profile untrusted --sandbox myapp -- bash")
    sys.exit(0)


def find_executables(overlay_dir: Path) -> list[Path]:
    """Find executable files in overlay directory, excluding caches."""
    skip_prefixes = (".cache/", ".local/share/", ".npm/", ".cargo/registry/")
    executables = []
    for path in overlay_dir.rglob("*"):
        if not path.is_file() or not os.access(path, os.X_OK):
            continue
        rel = str(path.relative_to(overlay_dir))
        if any(rel.startswith(p) for p in skip_prefixes):
            continue
        executables.append(path)
    return sorted(executables)


def generate_sandbox_alias(sandbox_name: str) -> None:
    """Scan sandbox for executables and output shell alias."""
    overlay_dir = Path.home() / ".local" / "state" / "bui" / "overlays" / sandbox_name

    if not overlay_dir.exists():
        print(f"Sandbox '{sandbox_name}' not found", file=sys.stderr)
        sys.exit(1)

    executables = find_executables(overlay_dir)
    if not executables:
        print(f"No executables found in sandbox '{sandbox_name}'", file=sys.stderr)
        sys.exit(1)

    print(f"Executables in sandbox '{sandbox_name}':")
    for i, exe in enumerate(executables, 1):
        print(f"  {i}. {exe.relative_to(overlay_dir)}")

    try:
        choice = input("\nSelect binary (number): ")
        selected = executables[int(choice) - 1]
    except (ValueError, IndexError, EOFError):
        print("Invalid selection", file=sys.stderr)
        sys.exit(1)

    binary_name = selected.name
    home_path = Path("~") / selected.relative_to(overlay_dir)

    print(f"\nAdd to your shell rc file:")
    print(f"  alias {binary_name}='bui --profile untrusted --sandbox {sandbox_name} --bind-cwd -- {home_path}'")


def parse_args() -> tuple[list[str], str | None, str | None, bool]:
    """Parse command line arguments.

    Returns: (command, profile_path, sandbox_name, bind_cwd)
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

    # Check for --sandbox flag (optional name for overlay isolation)
    sandbox_name = None
    if "--sandbox" in args:
        try:
            sandbox_idx = args.index("--sandbox")
            if sandbox_idx + 1 >= len(args) or args[sandbox_idx + 1].startswith("-"):
                print("Error: --sandbox requires a name", file=sys.stderr)
                sys.exit(1)
            sandbox_name = args[sandbox_idx + 1]
            # Remove --sandbox and its argument from args
            args = args[:sandbox_idx] + args[sandbox_idx + 2 :]
        except (IndexError, ValueError):
            pass

    # Check for --bind-cwd flag
    bind_cwd = "--bind-cwd" in args
    if bind_cwd:
        args.remove("--bind-cwd")

    # Check for --generate flag
    if "--generate" in args:
        args.remove("--generate")
        if sandbox_name is None:
            print("--generate requires --sandbox <name>", file=sys.stderr)
            sys.exit(1)
        generate_sandbox_alias(sandbox_name)
        sys.exit(0)

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
        if len(command) == 1:
            # Single string with shell metacharacters - pass directly to -c
            # (user already quoted it as a single argument)
            return ["/bin/bash", "-c", command[0]], profile_path, sandbox_name, bind_cwd
        else:
            # Multiple arguments with shell metacharacters - join them
            return ["/bin/bash", "-c", shlex.join(command)], profile_path, sandbox_name, bind_cwd
    return command, profile_path, sandbox_name, bind_cwd


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
