"""Filesystem configuration model."""

from pathlib import Path
from typing import ClassVar

from model.ui_field import ConfigBase, UIField


class FilesystemConfig(ConfigBase):
    """Filesystem mount settings for the sandbox."""

    # Virtual filesystems
    dev_mode = UIField(
        str, "minimal", "dev-mode-btn",
        "/dev mode", "Device access level",
        bwrap_args=lambda v: ["--dev", "/dev"] if v == "minimal" else
                             ["--bind", "/dev", "/dev"] if v == "full" else [],
    )
    mount_proc = UIField(
        bool, True, "opt-proc",
        "/proc", "Process info filesystem",
        bwrap_args=lambda v: ["--proc", "/proc"] if v else [],
    )
    mount_tmp = UIField(
        bool, True, "opt-tmp",
        "/tmp", "Ephemeral temp storage",
        # bwrap_args handled specially - needs tmpfs_size
    )
    tmpfs_size = UIField(
        str, "", "opt-tmpfs-size",
        "Tmpfs size", "Size limit for /tmp (e.g., 100M, 1G)",
        # Used together with mount_tmp
    )

    # System binds (read-only)
    bind_usr = UIField(
        bool, True, "opt-usr",
        "/usr", "Programs and libraries",
        bwrap_args=lambda v: ["--ro-bind", "/usr", "/usr"] if v and Path("/usr").exists() else [],
    )
    bind_bin = UIField(
        bool, True, "opt-bin",
        "/bin", "Essential binaries",
        bwrap_args=lambda v: ["--ro-bind", "/bin", "/bin"] if v and Path("/bin").exists() else [],
    )
    bind_lib = UIField(
        bool, True, "opt-lib",
        "/lib", "Shared libraries",
        bwrap_args=lambda v: ["--ro-bind", "/lib", "/lib"] if v and Path("/lib").exists() else [],
    )
    bind_lib64 = UIField(
        bool, True, "opt-lib64",
        "/lib64", "64-bit libraries",
        bwrap_args=lambda v: ["--ro-bind", "/lib64", "/lib64"] if v and Path("/lib64").exists() else [],
    )
    bind_sbin = UIField(
        bool, True, "opt-sbin",
        "/sbin", "System binaries",
        bwrap_args=lambda v: ["--ro-bind", "/sbin", "/sbin"] if v and Path("/sbin").exists() else [],
    )
    bind_etc = UIField(
        bool, False, "opt-etc",
        "/etc", "Config files - RISKY!",
        bwrap_args=lambda v: ["--ro-bind", "/etc", "/etc"] if v and Path("/etc").exists() else [],
    )

    # Class constant for path mapping (used by get_explanation)
    SYSTEM_PATHS: ClassVar[dict[str, str]] = {
        "bind_usr": "/usr",
        "bind_bin": "/bin",
        "bind_lib": "/lib",
        "bind_lib64": "/lib64",
        "bind_sbin": "/sbin",
        "bind_etc": "/etc",
    }
