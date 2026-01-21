"""UIField definitions for Virtual Filesystems group."""

from model.ui_field import UIField


def _named(name: str, field: UIField) -> UIField:
    """Set the name attribute on a UIField and return it."""
    field.name = name
    return field


dev_mode = _named("dev_mode", UIField(
    str, "minimal", "dev-mode-btn",
    "/dev mode", "Device access level",
    bwrap_args=lambda v: ["--dev", "/dev"] if v == "minimal" else
                         ["--bind", "/dev", "/dev"] if v == "full" else [],
))

mount_proc = _named("mount_proc", UIField(
    bool, True, "opt-proc",
    "/proc", "New procfs for sandbox",
    bwrap_args=lambda v: ["--proc", "/proc"] if v else [],
))

mount_tmp = _named("mount_tmp", UIField(
    bool, True, "opt-tmp",
    "/tmp", "Private temp filesystem",
    # Note: bwrap_args handled by group's custom to_args due to tmpfs_size dependency
))

tmpfs_size = _named("tmpfs_size", UIField(
    str, "", "opt-tmpfs-size",
    "Tmpfs size", "Size limit for /tmp (e.g., 100M, 1G)",
))
