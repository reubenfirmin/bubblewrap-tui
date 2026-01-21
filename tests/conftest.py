"""Shared fixtures for bubblewrap-tui tests."""

import os
from pathlib import Path

import pytest

from model import (
    BoundDirectory,
    FilterMode,
    HostnameFilter,
    IPFilter,
    NetworkFilter,
    OverlayConfig,
    PortForwarding,
    SandboxConfig,
)


@pytest.fixture
def mock_env(monkeypatch):
    """Clean environment for testing."""
    # Clear environment variables that affect detection
    monkeypatch.delenv("DISPLAY", raising=False)
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    monkeypatch.delenv("XDG_RUNTIME_DIR", raising=False)
    monkeypatch.delenv("DBUS_SESSION_BUS_ADDRESS", raising=False)
    monkeypatch.delenv("XAUTHORITY", raising=False)


@pytest.fixture
def minimal_config():
    """SandboxConfig with command only (defaults for everything else)."""
    return SandboxConfig(command=["bash"])


@pytest.fixture
def full_config():
    """SandboxConfig with many options enabled for comprehensive testing."""
    config = SandboxConfig(
        command=["python", "script.py", "--arg"],
        bound_dirs=[
            BoundDirectory(path=Path("/home/user/documents"), readonly=True),
            BoundDirectory(path=Path("/home/user/workspace"), readonly=False),
        ],
        overlays=[
            OverlayConfig(source="/home/user/data", dest="/data", mode="tmpfs"),
            OverlayConfig(
                source="/home/user/persist",
                dest="/persist",
                mode="persistent",
                write_dir="/var/persist-writes",
            ),
        ],
        drop_caps={"CAP_NET_RAW", "CAP_SYS_ADMIN"},
    )
    # Configure environment
    config.environment.clear_env = True
    config.environment.keep_env_vars = {"PATH", "HOME"}
    config.environment.custom_env_vars = {"MY_VAR": "my_value"}

    # Configure hostname
    config.hostname.custom_hostname = "sandbox"

    # Configure filesystem
    config.filesystem.dev_mode = "minimal"
    config.filesystem.mount_proc = True
    config.filesystem.mount_tmp = True
    config.filesystem.tmpfs_size = "100M"
    config.filesystem.bind_usr = True
    config.filesystem.bind_bin = True
    config.filesystem.bind_lib = True
    config.filesystem.bind_etc = False

    # Configure network
    config.network.share_net = True
    config.network.bind_resolv_conf = True
    config.network.bind_ssl_certs = True

    # Configure desktop
    config.desktop.allow_dbus = False
    config.desktop.allow_display = False
    config.desktop.bind_user_config = False

    # Configure user identity
    config.user.unshare_user = True
    config.user.uid = 1000
    config.user.gid = 1000

    # Configure namespace (without unshare_user - that's in user group now)
    config.namespace.unshare_pid = True
    config.namespace.unshare_ipc = True

    # Configure process
    config.process.die_with_parent = True
    config.process.new_session = True
    config.process.as_pid_1 = False
    config.process.chdir = "/home/user"

    return config


@pytest.fixture
def tmp_profile(tmp_path):
    """Temporary directory for profile files."""
    profile_dir = tmp_path / "profiles"
    profile_dir.mkdir()
    return profile_dir


@pytest.fixture
def bound_dir_readonly():
    """A readonly bound directory."""
    return BoundDirectory(path=Path("/home/user/documents"), readonly=True)


@pytest.fixture
def bound_dir_readwrite():
    """A read-write bound directory."""
    return BoundDirectory(path=Path("/tmp/workspace"), readonly=False)


@pytest.fixture
def overlay_tmpfs():
    """An empty tmpfs directory (no source needed)."""
    return OverlayConfig(source="", dest="/data", mode="tmpfs")


@pytest.fixture
def overlay_overlay():
    """An overlay with source (writable layer on existing dir, changes in RAM)."""
    return OverlayConfig(source="/home/user/data", dest="/data", mode="overlay")


@pytest.fixture
def overlay_persistent():
    """A persistent overlay configuration."""
    return OverlayConfig(
        source="/home/user/persist",
        dest="/persist",
        mode="persistent",
        write_dir="/var/persist-writes",
    )


@pytest.fixture
def network_filter_whitelist():
    """A NetworkFilter with whitelist mode."""
    return NetworkFilter(
        enabled=True,
        hostname_filter=HostnameFilter(
            mode=FilterMode.WHITELIST,
            hosts=["github.com", "registry.npmjs.org"],
        ),
        ip_filter=IPFilter(
            mode=FilterMode.OFF,
            cidrs=[],
        ),
        port_forwarding=PortForwarding(host_ports=[5432, 6379]),
    )


@pytest.fixture
def network_filter_blacklist():
    """A NetworkFilter with blacklist mode."""
    return NetworkFilter(
        enabled=True,
        hostname_filter=HostnameFilter(
            mode=FilterMode.OFF,
            hosts=[],
        ),
        ip_filter=IPFilter(
            mode=FilterMode.BLACKLIST,
            cidrs=["10.0.0.0/8", "192.168.0.0/16"],
        ),
    )
