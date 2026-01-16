"""Command-line interface for bui."""

import os
import shutil
import sys
from pathlib import Path

from app import BubblewrapTUI

BUI_VERSION = "0.3.2"
BUI_RELEASE_URL = "https://github.com/reubenfirmin/bubblewrap-tui/releases/latest/download/bui"


def get_install_path() -> Path:
    """Get the installation path."""
    return Path.home() / ".local" / "bin" / "bui"


def is_local_bin_on_path() -> bool:
    """Check if ~/.local/bin is on PATH."""
    local_bin = str(Path.home() / ".local" / "bin")
    return local_bin in os.environ.get("PATH", "").split(os.pathsep)


def do_install(source_path: Path | None = None) -> None:
    """Install bui to ~/.local/bin."""
    local_bin = Path.home() / ".local" / "bin"
    install_path = local_bin / "bui"

    if not is_local_bin_on_path():
        print("~/.local/bin is not on your PATH.")
        print("\nTo add it, add this line to your shell rc file (~/.bashrc, ~/.zshrc, etc.):")
        print('  export PATH="$HOME/.local/bin:$PATH"')
        print("\nThen restart your shell or run: source ~/.bashrc")
        sys.exit(1)

    # Create directory if needed
    local_bin.mkdir(parents=True, exist_ok=True)

    # Copy the script
    if source_path is None:
        source_path = Path(__file__).resolve()

    shutil.copy2(source_path, install_path)
    install_path.chmod(0o755)

    print(f"Installed bui v{BUI_VERSION} to {install_path}")


def do_update() -> None:
    """Download latest bui from GitHub and install."""
    import tempfile
    import urllib.request

    print("Downloading latest bui from GitHub...")

    try:
        with urllib.request.urlopen(BUI_RELEASE_URL) as response:
            content = response.read()
    except Exception as e:
        print(f"Error downloading: {e}", file=sys.stderr)
        sys.exit(1)

    # Write to temp file
    with tempfile.NamedTemporaryFile(mode='wb', suffix='.py', delete=False) as f:
        f.write(content)
        temp_path = Path(f.name)

    try:
        temp_path.chmod(0o755)
        do_install(temp_path)
    finally:
        temp_path.unlink()


def needs_shell_wrap(command: list[str]) -> bool:
    """Check if command needs to be wrapped in a shell."""
    if len(command) != 1:
        return False
    cmd = command[0]
    shell_chars = ['|', '&&', '||', ';', '>', '<', '$(', '`']
    return any(c in cmd for c in shell_chars)


def show_help() -> None:
    """Print help message and exit."""
    print(__doc__ or "Bubblewrap TUI - A visual interface for configuring bubblewrap sandboxes.")
    print(f"Version: {BUI_VERSION}")
    print("\nUsage:")
    print("  bui -- <command> [args...]   Configure and run a sandboxed command")
    print("  bui --install                Install bui to ~/.local/bin")
    print("  bui --update                 Download latest version and install")
    print("\nExamples:")
    print("  bui -- /bin/bash")
    print("  bui -- python script.py arg1 arg2")
    print('  bui -- "curl foo.sh | bash"    (pipes and redirects auto-handled)')
    sys.exit(0)


def parse_args() -> list[str]:
    """Parse command line arguments."""
    args = sys.argv[1:]

    if not args or "--help" in args or "-h" in args:
        show_help()

    if "--install" in args:
        do_install()
        sys.exit(0)

    if "--update" in args:
        do_update()
        sys.exit(0)

    try:
        sep_idx = args.index("--")
        command = args[sep_idx + 1:]
        if not command:
            print("Error: No command specified after '--'", file=sys.stderr)
            print("Usage: bui -- <command> [args...]", file=sys.stderr)
            sys.exit(1)
    except ValueError:
        command = args

    if needs_shell_wrap(command):
        return ["/bin/bash", "-c", command[0]]
    return command


def main() -> None:
    """Main entry point."""
    command = parse_args()

    app = BubblewrapTUI(command, version=BUI_VERSION)
    app.run()

    if app._execute_command:
        cmd = app.config.build_command()
        print("\n" + "=" * 60)
        print("Executing:")
        print(" ".join(cmd))
        print("=" * 60 + "\n")

        os.execvp("bwrap", cmd)
    else:
        print("Cancelled.")
        sys.exit(0)


if __name__ == "__main__":
    main()
