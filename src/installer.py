"""Installation and update utilities for bui."""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

BUI_RELEASE_URL = "https://github.com/reubenfirmin/bubblewrap-tui/releases/latest/download/bui"
BUI_API_URL = "https://api.github.com/repos/reubenfirmin/bubblewrap-tui/releases/latest"
UPDATE_CHECK_INTERVAL = 86400  # 1 day in seconds


def get_cache_dir() -> Path:
    """Get the cache directory for bui."""
    cache_dir = Path.home() / ".cache" / "bui"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir


def get_install_path() -> Path:
    """Get the installation path."""
    return Path.home() / ".local" / "bin" / "bui"


def is_local_bin_on_path() -> bool:
    """Check if ~/.local/bin is on PATH."""
    local_bin = str(Path.home() / ".local" / "bin")
    return local_bin in os.environ.get("PATH", "").split(os.pathsep)


def should_check_for_updates() -> bool:
    """Check if enough time has passed since last update check."""
    last_check_file = get_cache_dir() / "last_update_check"
    if not last_check_file.exists():
        return True
    try:
        last_check = float(last_check_file.read_text().strip())
        return (time.time() - last_check) > UPDATE_CHECK_INTERVAL
    except (ValueError, OSError):
        return True


def record_update_check() -> None:
    """Record that we just checked for updates."""
    last_check_file = get_cache_dir() / "last_update_check"
    last_check_file.write_text(str(time.time()))


def parse_version(version: str) -> tuple[int, ...]:
    """Parse version string into comparable tuple."""
    version = version.lstrip("v")
    try:
        return tuple(int(p) for p in version.split("."))
    except ValueError:
        return (0,)


def check_for_updates(current_version: str) -> str | None:
    """Check GitHub for a newer version.

    Args:
        current_version: Current version string

    Returns:
        New version string if available, None otherwise
    """
    import json

    if not should_check_for_updates():
        return None

    try:
        req = urllib.request.Request(
            BUI_API_URL, headers={"Accept": "application/vnd.github.v3+json"}
        )
        with urllib.request.urlopen(req, timeout=5) as response:
            data = json.loads(response.read().decode())
            latest_version = data.get("tag_name", "")

        record_update_check()

        if parse_version(latest_version) > parse_version(current_version):
            return latest_version
    except Exception:
        pass

    return None


def do_install(version: str, source_path: Path | None = None) -> None:
    """Install bui to ~/.local/bin.

    Args:
        version: Version string for display
        source_path: Source file to install (defaults to current script)
    """
    local_bin = Path.home() / ".local" / "bin"
    install_path = local_bin / "bui"

    if not is_local_bin_on_path():
        print("~/.local/bin is not on your PATH.")
        print("\nTo add it, add this line to your shell rc file (~/.bashrc, ~/.zshrc, etc.):")
        print('  export PATH="$HOME/.local/bin:$PATH"')
        print("\nThen restart your shell or run: source ~/.bashrc")
        sys.exit(1)

    local_bin.mkdir(parents=True, exist_ok=True)

    if source_path is None:
        source_path = Path(__file__).resolve()

    shutil.copy2(source_path, install_path)
    install_path.chmod(0o755)

    print(f"Installed bui v{version} to {install_path}")


def do_update(version: str) -> None:
    """Download latest bui from GitHub and install.

    Args:
        version: Current version string for display after install
    """
    print("Downloading latest bui from GitHub...")

    try:
        with urllib.request.urlopen(BUI_RELEASE_URL) as response:
            content = response.read()
    except Exception as e:
        print(f"Error downloading: {e}", file=sys.stderr)
        sys.exit(1)

    with tempfile.NamedTemporaryFile(mode="wb", suffix=".py", delete=False) as f:
        f.write(content)
        temp_path = Path(f.name)

    try:
        temp_path.chmod(0o755)
        do_install(version, temp_path)
    finally:
        temp_path.unlink()


def show_update_notice(current_version: str, new_version: str) -> None:
    """Display update available notice.

    Args:
        current_version: Current version string
        new_version: Available version string
    """
    msg1 = f"Update available: {current_version} -> {new_version}"
    msg2 = "Run 'bui --update' to install the latest version."
    width = max(len(msg1), len(msg2)) + 4
    print()
    print(f"┌{'─' * width}┐")
    print(f"│  {msg1.ljust(width - 2)}│")
    print(f"│  {msg2.ljust(width - 2)}│")
    print(f"└{'─' * width}┘")
    print()
