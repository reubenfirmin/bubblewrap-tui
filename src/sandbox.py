"""Sandbox lifecycle management functions."""

import json
import os
import shlex
import shutil
import sys
from pathlib import Path

from profiles import BUI_PROFILES_DIR, Profile

# Base directory for overlay storage
BUI_STATE_DIR = Path.home() / ".local" / "state" / "bui"

# Sandbox directory structure
# Each sandbox contains its own overlays subdirectory
BUI_SANDBOXES_DIR = BUI_STATE_DIR / "sandboxes"

# Metadata file tracking installed wrapper scripts
INSTALLED_SCRIPTS_FILE = BUI_STATE_DIR / "installed.json"


def normalize_dest_path(dest: str) -> str:
    """Normalize a mount destination path to a safe directory name.

    Converts paths like '/home/sandbox' to 'home-sandbox' and '/usr' to 'usr'.

    Args:
        dest: The mount destination path (e.g., '/home/sandbox', '/usr')

    Returns:
        A normalized string safe for use as a directory name

    Note:
        Paths with dashes in component names (e.g., '/my-app') cannot be
        perfectly round-tripped. See denormalize_dest_path().
    """
    # Strip leading/trailing slashes and replace remaining slashes with dashes
    normalized = dest.strip("/").replace("/", "-")
    # Handle edge case of empty string (root mount)
    return normalized if normalized else "root"


def denormalize_dest_path(normalized: str) -> str:
    """Convert normalized directory name back to mount path.

    Converts 'home-sandbox' to '/home/sandbox' and 'usr' to '/usr'.

    Args:
        normalized: The normalized directory name

    Returns:
        The reconstructed mount path

    Note:
        This is a best-effort reverse of normalize_dest_path(). Paths with
        dashes in component names (e.g., '/my-app') will be incorrectly
        reconstructed as '/my/app'. This only affects the display of
        executable paths in --install mode.
    """
    if normalized == "root":
        return "/"
    return "/" + normalized.replace("-", "/")


def get_sandbox_dir(sandbox_name: str) -> Path:
    """Get the root directory for a sandbox.

    Args:
        sandbox_name: Name of the sandbox

    Returns:
        Path to sandbox directory: ~/.local/state/bui/sandboxes/{sandbox_name}/
    """
    return BUI_SANDBOXES_DIR / sandbox_name


def get_overlay_write_dir(sandbox_name: str, dest: str) -> Path:
    """Get the write directory for a specific overlay within a sandbox.

    Args:
        sandbox_name: Name of the sandbox
        dest: Mount destination path (e.g., '/home/sandbox', '/usr')

    Returns:
        Path to overlay write directory:
        ~/.local/state/bui/sandboxes/{sandbox_name}/overlays/{normalized_dest}/
    """
    normalized = normalize_dest_path(dest)
    return get_sandbox_dir(sandbox_name) / "overlays" / normalized


def get_sandbox_work_dir(sandbox_name: str) -> Path:
    """Get the shared work directory for a sandbox.

    All overlays in a sandbox share a single work directory.

    Args:
        sandbox_name: Name of the sandbox

    Returns:
        Path to work directory: ~/.local/state/bui/sandboxes/{sandbox_name}/.overlay-work/
    """
    return get_sandbox_dir(sandbox_name) / ".overlay-work"


def _load_installed() -> dict[str, dict]:
    """Load installed scripts metadata. Returns {sandbox_name: {scripts: [...], profile: ...}}."""
    if not INSTALLED_SCRIPTS_FILE.exists():
        return {}
    try:
        return json.loads(INSTALLED_SCRIPTS_FILE.read_text())
    except (json.JSONDecodeError, OSError):
        return {}


def cleanup_orphaned_sandboxes() -> None:
    """Clean up orphaned sandboxes from previous runs.

    Any sandbox directory not in installed.json is orphaned.
    """
    if not BUI_SANDBOXES_DIR.exists():
        return

    installed = _load_installed()

    for sandbox_dir in BUI_SANDBOXES_DIR.iterdir():
        if not sandbox_dir.is_dir():
            continue
        if sandbox_dir.name not in installed:
            _fix_overlay_workdir_permissions(sandbox_dir)
            shutil.rmtree(sandbox_dir, ignore_errors=True)


def _save_installed(installed: dict[str, dict]) -> None:
    """Save installed scripts metadata."""
    INSTALLED_SCRIPTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    INSTALLED_SCRIPTS_FILE.write_text(json.dumps(installed, indent=2))


def register_sandbox(
    sandbox_name: str,
    profile: str,
    bind_paths: list[str] | None = None,
    bind_env: list[str] | None = None,
) -> None:
    """Register a sandbox in metadata (before installing scripts)."""
    installed = _load_installed()
    if sandbox_name not in installed:
        installed[sandbox_name] = {"scripts": [], "profile": profile}
        if bind_paths:
            installed[sandbox_name]["bind_paths"] = bind_paths
        if bind_env:
            installed[sandbox_name]["bind_env"] = bind_env
        _save_installed(installed)


def _add_installed(
    sandbox_name: str,
    script_name: str,
    profile: str,
    bind_paths: list[str] | None = None,
    bind_env: list[str] | None = None,
) -> None:
    """Record that a script was installed for a sandbox."""
    installed = _load_installed()
    if sandbox_name not in installed:
        installed[sandbox_name] = {"scripts": [], "profile": profile}
        if bind_paths:
            installed[sandbox_name]["bind_paths"] = bind_paths
        if bind_env:
            installed[sandbox_name]["bind_env"] = bind_env
    if script_name not in installed[sandbox_name]["scripts"]:
        installed[sandbox_name]["scripts"].append(script_name)
    _save_installed(installed)


def _remove_installed(sandbox_name: str) -> list[str]:
    """Remove sandbox from installed metadata. Returns list of script names."""
    installed = _load_installed()
    entry = installed.pop(sandbox_name, {})
    _save_installed(installed)
    # Handle both old format (list) and new format (dict with scripts key)
    if isinstance(entry, list):
        return entry
    return entry.get("scripts", [])


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


def install_sandbox_binary(
    sandbox_name: str,
    profile: str = "untrusted",
    bind_paths: list[str] | None = None,
    bind_env: list[str] | None = None,
) -> None:
    """Install selected binary from sandbox to ~/.local/bin."""
    sandbox_dir = get_sandbox_dir(sandbox_name)
    overlays_dir = sandbox_dir / "overlays"
    bin_dir = Path.home() / ".local" / "bin"

    if not overlays_dir.exists():
        print(f"Sandbox '{sandbox_name}' not found", file=sys.stderr)
        sys.exit(1)

    # Read existing metadata to get binds if not provided
    installed = _load_installed()
    if sandbox_name in installed:
        entry = installed[sandbox_name]
        if profile == "untrusted" and entry.get("profile"):
            profile = entry["profile"]
        if bind_paths is None:
            bind_paths = entry.get("bind_paths")
        if bind_env is None:
            bind_env = entry.get("bind_env")

    # Search all overlay subdirectories for executables
    all_executables: list[tuple[Path, str]] = []  # (path, sandbox_mount_point)
    for overlay_subdir in overlays_dir.iterdir():
        if not overlay_subdir.is_dir():
            continue
        # Map overlay dirname back to mount point (e.g., "home-sandbox" -> "/home/sandbox")
        mount_point = denormalize_dest_path(overlay_subdir.name)
        executables = find_executables(overlay_subdir)
        for exe in executables:
            rel_path = exe.relative_to(overlay_subdir)
            all_executables.append((exe, f"{mount_point}/{rel_path}"))

    if not all_executables:
        print(f"No executables found in sandbox '{sandbox_name}'", file=sys.stderr)
        sys.exit(1)

    print(f"Executables in sandbox '{sandbox_name}':")
    for i, (exe, sandbox_path) in enumerate(all_executables, 1):
        print(f"  {i}. {sandbox_path}")

    try:
        choice = input("\nSelect binary (number): ")
        selected_exe, selected_sandbox_path = all_executables[int(choice) - 1]
    except (ValueError, IndexError, EOFError):
        print("Invalid selection", file=sys.stderr)
        sys.exit(1)

    binary_name = selected_exe.name
    # Path inside sandbox is already computed
    home_path = selected_sandbox_path
    script_path = bin_dir / binary_name

    bin_dir.mkdir(parents=True, exist_ok=True)

    # Build extra flags for bind paths and env vars
    # All values are shell-quoted to prevent command injection
    extra_flags = ""
    if bind_paths:
        for p in bind_paths:
            extra_flags += f" --bind {shlex.quote(p)}"
    if bind_env:
        for env_spec in bind_env:
            extra_flags += f" --bind-env {shlex.quote(env_spec)}"

    script_content = f"""#!/bin/sh
exec bui --profile {shlex.quote(profile)} --sandbox {shlex.quote(sandbox_name)} --bind-cwd{extra_flags} -- {shlex.quote(home_path)} "$@"
"""
    script_path.write_text(script_content)
    script_path.chmod(0o755)
    _add_installed(sandbox_name, binary_name, profile, bind_paths, bind_env)
    print(f"Installed: {script_path}")


def _fix_overlay_workdir_permissions(path: Path) -> None:
    """Fix permissions on overlayfs workdir before deletion.

    Overlayfs sets workdir permissions to 000 to prevent direct access.
    Since the user owns the directory, we can chmod it to allow deletion.
    """
    for root, dirs, files in os.walk(path, topdown=True):
        for d in dirs:
            dir_path = Path(root) / d
            try:
                # Ensure we can read/write/execute the directory
                current_mode = dir_path.stat().st_mode
                if current_mode & 0o700 != 0o700:
                    os.chmod(dir_path, current_mode | 0o700)
            except OSError:
                pass


def uninstall_sandbox(sandbox_name: str) -> None:
    """Remove sandbox: wrapper scripts in ~/.local/bin and overlay data."""
    sandbox_dir = get_sandbox_dir(sandbox_name)
    bin_dir = Path.home() / ".local" / "bin"

    installed = _load_installed()
    has_sandbox = sandbox_dir.exists()
    has_metadata = sandbox_name in installed

    if not has_sandbox and not has_metadata:
        print(f"Sandbox '{sandbox_name}' not found", file=sys.stderr)
        sys.exit(1)

    scripts_to_remove = _remove_installed(sandbox_name)
    for script_name in scripts_to_remove:
        script_path = bin_dir / script_name
        if script_path.exists():
            script_path.unlink()
            print(f"Removed: {script_path}")

    if has_sandbox:
        # Fix permissions on overlay workdir (overlayfs sets to 000)
        _fix_overlay_workdir_permissions(sandbox_dir)
        shutil.rmtree(sandbox_dir)
        print(f"Removed: {sandbox_dir}/")


def list_sandboxes() -> None:
    """List installed sandboxes from metadata."""
    installed = _load_installed()

    if not installed:
        print("No sandboxes installed")
        print("(use --list-overlays to see overlay directories)")
        return

    print("Sandboxes:")
    for name in sorted(installed.keys()):
        entry = installed[name]
        scripts = entry.get("scripts", []) if isinstance(entry, dict) else entry
        profile = entry.get("profile", "untrusted") if isinstance(entry, dict) else "untrusted"
        bind_paths = entry.get("bind_paths", []) if isinstance(entry, dict) else []
        bind_env = entry.get("bind_env", []) if isinstance(entry, dict) else []
        print(f"  {name}")
        print(f"    profile: {profile}")
        if scripts:
            print(f"    scripts: {', '.join(sorted(scripts))}")
        else:
            print(f"    scripts: (none - run: bui --sandbox {name} --install)")
        if bind_paths:
            print(f"    bind: {', '.join(bind_paths)}")
        if bind_env:
            print(f"    bind-env: {', '.join(bind_env)}")


def list_overlays() -> None:
    """List all sandbox directories with their overlays."""
    installed = _load_installed()
    found_any = False

    if BUI_SANDBOXES_DIR.exists():
        sandboxes = sorted(
            d for d in BUI_SANDBOXES_DIR.iterdir()
            if d.is_dir() and not d.name.startswith(".")
        )
        for sandbox_dir in sandboxes:
            name = sandbox_dir.name
            overlays_subdir = sandbox_dir / "overlays"
            if not overlays_subdir.exists():
                continue
            found_any = True
            file_count = sum(1 for _ in sandbox_dir.rglob("*") if _.is_file())
            has_installed = name in installed
            overlay_names = sorted(
                d.name for d in overlays_subdir.iterdir()
                if d.is_dir() and not d.name.startswith(".")
            )

            print(f"  {sandbox_dir}/")
            print(f"    overlays: {', '.join(overlay_names) if overlay_names else '(empty)'}")
            print(f"    files: {file_count}")
            if has_installed:
                print(f"    To remove: bui --sandbox {name} --uninstall")
            else:
                print("    No scripts installed (safe to delete)")

    if not found_any:
        print("No sandboxes found")


def list_profiles() -> None:
    """List available profiles."""
    profiles = Profile.list_profiles(BUI_PROFILES_DIR)

    if not profiles:
        print("No profiles found")
        print(f"(profiles are stored in {BUI_PROFILES_DIR})")
        return

    print("Profiles:")
    for profile in profiles:
        print(f"  {profile.name}")
    print(f"\nProfile directory: {BUI_PROFILES_DIR}")


def clean_temp_files() -> None:
    """Remove temporary network filter directories from /tmp."""
    import shutil
    import tempfile

    removed = 0
    errors = 0

    # Check /tmp for bui-* temp directories
    tmp_dir = Path(tempfile.gettempdir())
    for pattern in ["bui-net-*", "bui-audit-*", "bui-vfiles-*"]:
        for item in tmp_dir.glob(pattern):
            if item.is_dir():
                try:
                    shutil.rmtree(item)
                    print(f"  Removed: {item}")
                    removed += 1
                except OSError as e:
                    print(f"  Error removing {item}: {e}")
                    errors += 1

    if removed == 0 and errors == 0:
        print("No temporary files found.")
    else:
        print(f"\nCleaned up {removed} temporary director{'y' if removed == 1 else 'ies'}.")
        if errors:
            print(f"Failed to remove {errors} director{'y' if errors == 1 else 'ies'}.")
