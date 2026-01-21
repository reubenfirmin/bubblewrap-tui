"""Sandbox lifecycle management functions."""

import json
import os
import shutil
import sys
from pathlib import Path

from profiles import BUI_PROFILES_DIR, Profile

# Base directory for overlay storage
BUI_STATE_DIR = Path.home() / ".local" / "state" / "bui"

# Metadata file tracking installed wrapper scripts
INSTALLED_SCRIPTS_FILE = BUI_STATE_DIR / "installed.json"


def _load_installed() -> dict[str, dict]:
    """Load installed scripts metadata. Returns {sandbox_name: {scripts: [...], profile: ...}}."""
    if not INSTALLED_SCRIPTS_FILE.exists():
        return {}
    try:
        return json.loads(INSTALLED_SCRIPTS_FILE.read_text())
    except (json.JSONDecodeError, OSError):
        return {}


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
    overlay_dir = BUI_STATE_DIR / "overlays" / sandbox_name
    bin_dir = Path.home() / ".local" / "bin"

    if not overlay_dir.exists():
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
    # Path inside sandbox - overlay is bound to /home/sandbox
    sandbox_home = "/home/sandbox"
    home_path = f"{sandbox_home}/{selected.relative_to(overlay_dir)}"
    script_path = bin_dir / binary_name

    bin_dir.mkdir(parents=True, exist_ok=True)

    # Build extra flags for bind paths and env vars
    extra_flags = ""
    if bind_paths:
        for p in bind_paths:
            extra_flags += f" --bind {p}"
    if bind_env:
        for env_spec in bind_env:
            extra_flags += f" --bind-env '{env_spec}'"

    script_content = f"""#!/bin/sh
exec bui --profile {profile} --sandbox {sandbox_name} --bind-cwd{extra_flags} -- {home_path} "$@"
"""
    script_path.write_text(script_content)
    script_path.chmod(0o755)
    _add_installed(sandbox_name, binary_name, profile, bind_paths, bind_env)
    print(f"Installed: {script_path}")


def uninstall_sandbox(sandbox_name: str) -> None:
    """Remove sandbox: wrapper scripts in ~/.local/bin and overlay data."""
    overlay_dir = BUI_STATE_DIR / "overlays" / sandbox_name
    bin_dir = Path.home() / ".local" / "bin"

    # Check if sandbox exists (either overlay dir or metadata)
    installed = _load_installed()
    has_overlay = overlay_dir.exists()
    has_metadata = sandbox_name in installed

    if not has_overlay and not has_metadata:
        print(f"Sandbox '{sandbox_name}' not found", file=sys.stderr)
        sys.exit(1)

    # Remove wrapper scripts tracked in metadata
    scripts_to_remove = _remove_installed(sandbox_name)
    for script_name in scripts_to_remove:
        script_path = bin_dir / script_name
        if script_path.exists():
            script_path.unlink()
            print(f"Removed: {script_path}")

    # Remove overlay directory if it exists
    if has_overlay:
        shutil.rmtree(overlay_dir)
        print(f"Removed: {overlay_dir}/")


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
    """List all overlay directories with details."""
    overlays_dir = BUI_STATE_DIR / "overlays"

    if not overlays_dir.exists():
        print("No overlays found")
        return

    overlays = sorted(
        d for d in overlays_dir.iterdir() if d.is_dir() and not d.name.startswith(".")
    )

    if not overlays:
        print("No overlays found")
        return

    # Load installed sandboxes to check associations
    installed = _load_installed()

    print("Overlays:")
    for overlay in overlays:
        name = overlay.name
        # Count files
        file_count = sum(1 for _ in overlay.rglob("*") if _.is_file())
        # Check if associated with installed sandbox
        has_sandbox = name in installed

        print(f"  {overlay}/")
        print(f"    files: {file_count}")
        if has_sandbox:
            print(f"    To remove: bui --sandbox {name} --uninstall")
        else:
            print("    No sandbox installed (safe to delete)")


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

    tmp_dir = Path(tempfile.gettempdir())
    removed = 0
    errors = 0

    # Find bui-net-* directories
    for item in tmp_dir.glob("bui-net-*"):
        if item.is_dir():
            try:
                shutil.rmtree(item)
                print(f"  Removed: {item}")
                removed += 1
            except OSError as e:
                print(f"  Error removing {item}: {e}")
                errors += 1

    if removed == 0 and errors == 0:
        print("No temporary network filter files found.")
    else:
        print(f"\nCleaned up {removed} temporary director{'y' if removed == 1 else 'ies'}.")
        if errors:
            print(f"Failed to remove {errors} director{'y' if errors == 1 else 'ies'}.")
