"""Installation and update utilities for bui."""

from __future__ import annotations

import json
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


def get_config_dir() -> Path:
    """Get the config directory for bui."""
    config_dir = Path.home() / ".config" / "bui"
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir


def get_profiles_dir() -> Path:
    """Get the profiles directory for bui."""
    profiles_dir = get_config_dir() / "profiles"
    profiles_dir.mkdir(parents=True, exist_ok=True)
    return profiles_dir


def create_default_profiles() -> None:
    """Create default profiles if they don't exist."""
    profiles_dir = get_profiles_dir()
    untrusted_profile = profiles_dir / "untrusted.json"

    home = str(Path.home())
    overlay_write_dir = Path.home() / ".local" / "state" / "bui" / "overlays"
    overlay_work_dir = Path.home() / ".local" / "state" / "bui" / ".overlay-work"

    # Always create overlay directories
    overlay_write_dir.mkdir(parents=True, exist_ok=True)
    overlay_work_dir.mkdir(parents=True, exist_ok=True)

    # Always create/overwrite default profiles
    # User customizations should be saved under different names

    # Build bound_dirs for system paths that exist
    # Note: /etc is NOT included - only specific files needed for networking/SSL
    # are bound via detection (resolv.conf, nsswitch.conf, SSL certs)
    bound_dirs = []
    for path_str in ["/usr", "/bin", "/lib", "/lib64", "/sbin"]:
        if Path(path_str).exists():
            bound_dirs.append({"path": path_str, "readonly": True})

    # Use a non-root virtual user so tools like npm install to home instead of system
    profile_data = {
        "bound_dirs": bound_dirs,
        "overlays": [
            {
                "source": "",
                "dest": "/home/sandbox",  # Home for virtual user
                "mode": "persistent",  # Persist changes to overlay dir (customized per --sandbox)
                "write_dir": str(overlay_write_dir),
            }
        ],
        "drop_caps": [],
        "_vfs_group": {
            "_values": {
                "dev_mode": "minimal",
                "mount_proc": True,
                "mount_tmp": True,
                "tmpfs_size": "",
            }
        },
        # Note: _system_paths_group is NOT included - it's UI-only state
        # Checkbox states are derived from bound_dirs when loading a profile
        # Note: overlay_home is UI-only - derived from overlays list
        "_user_group": {
            "_values": {
                "unshare_user": True,
                "uid": 1000,
                "gid": 1000,
                "username": "sandbox",
                "synthetic_passwd": True,  # Generate /etc/passwd and /etc/group
            }
        },
        "_isolation_group": {
            "_values": {
                "unshare_pid": True,
                "unshare_ipc": True,
                "unshare_cgroup": True,
                "disable_userns": False,
                # Use seccomp instead of bwrap's --disable-userns because network
                # filtering requires CAP_NET_ADMIN which conflicts with --disable-userns
                "seccomp_block_userns": True,
            }
        },
        "_hostname_group": {
            "_values": {
                "unshare_uts": True,
                "custom_hostname": "sandbox",
            }
        },
        "_process_group": {
            "_values": {
                "die_with_parent": True,
                "new_session": True,
                "as_pid_1": False,
                "chdir": "",
            }
        },
        "_network_group": {
            "_values": {
                "share_net": True,
                "bind_resolv_conf": True,
                "bind_ssl_certs": True,
            }
        },
        "_desktop_group": {
            "_values": {
                "allow_dbus": False,
                "allow_display": False,
                "bind_user_config": False,
            }
        },
        "_environment_group": {
            "_values": {
                "clear_env": True,
                "keep_env_vars": ["TERM"],  # Needed for terminal colors
                "unset_env_vars": [],
                "custom_env_vars": {
                    "HOME": "/home/sandbox",
                    "PATH": "/usr/local/bin:/usr/bin:/bin:/usr/local/sbin:/usr/sbin:/sbin",
                },
            }
        },
        # Block localhost and local network access to prevent untrusted code
        # from accessing local services (databases, web servers, etc.)
        "network_filter": {
            "mode": "filter",
            "hostname_filter": {
                "mode": "off",
                "hosts": []
            },
            "ip_filter": {
                "mode": "blacklist",
                "cidrs": [
                    # Loopback
                    "127.0.0.0/8",
                    "::1/128",
                    # Private networks
                    "10.0.0.0/8",
                    "172.16.0.0/12",
                    "192.168.0.0/16",
                    # Link-local
                    "169.254.0.0/16",
                    "fe80::/10",
                    # IPv6 unique local
                    "fc00::/7",
                ]
            },
            "port_forwarding": {
                "expose_ports": [],
                "host_ports": []
            },
            "audit": {
                "pcap_path": None
            }
        },
    }

    untrusted_profile.write_text(json.dumps(profile_data, indent=2))
    print(f"Created default profile: {untrusted_profile}")


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

    # Create default profiles
    create_default_profiles()


def get_latest_version() -> str | None:
    """Fetch the latest version tag from GitHub.

    Returns:
        Latest version string, or None if fetch fails
    """
    import json

    try:
        req = urllib.request.Request(
            BUI_API_URL, headers={"Accept": "application/vnd.github.v3+json"}
        )
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode())
            return data.get("tag_name", "").lstrip("v")
    except Exception:
        return None


def do_update(current_version: str) -> None:
    """Download latest bui from GitHub and install.

    Args:
        current_version: Current version string for comparison
    """
    # Get the latest version first
    latest_version = get_latest_version()
    if latest_version:
        print(f"Downloading bui v{latest_version} from GitHub...")
    else:
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
        # Use the latest version for the install message
        do_install(latest_version or current_version, temp_path)
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
