"""Shared fixtures for bubblewrap-tui tests."""

import os
from pathlib import Path

import pytest

from model import (
    BoundDirectory,
    DesktopConfig,
    EnvironmentConfig,
    FilesystemConfig,
    NamespaceConfig,
    NetworkConfig,
    OverlayConfig,
    ProcessConfig,
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
    return SandboxConfig(
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
        environment=EnvironmentConfig(
            clear_env=True,
            custom_hostname="sandbox",
            keep_env_vars={"PATH", "HOME"},
            custom_env_vars={"MY_VAR": "my_value"},
        ),
        filesystem=FilesystemConfig(
            dev_mode="minimal",
            mount_proc=True,
            mount_tmp=True,
            tmpfs_size="100M",
            bind_usr=True,
            bind_bin=True,
            bind_lib=True,
            bind_etc=False,
        ),
        network=NetworkConfig(
            share_net=True,
            bind_resolv_conf=True,
            bind_ssl_certs=True,
        ),
        desktop=DesktopConfig(
            allow_dbus=False,
            allow_display=False,
            bind_user_config=False,
        ),
        namespace=NamespaceConfig(
            unshare_user=True,
            unshare_pid=True,
            unshare_ipc=True,
        ),
        process=ProcessConfig(
            die_with_parent=True,
            new_session=True,
            as_pid_1=False,
            chdir="/home/user",
            uid=1000,
            gid=1000,
        ),
    )


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
    """A tmpfs overlay configuration."""
    return OverlayConfig(source="/home/user/data", dest="/data", mode="tmpfs")


@pytest.fixture
def overlay_persistent():
    """A persistent overlay configuration."""
    return OverlayConfig(
        source="/home/user/persist",
        dest="/persist",
        mode="persistent",
        write_dir="/var/persist-writes",
    )
