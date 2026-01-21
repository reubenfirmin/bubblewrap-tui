"""UIField definitions for System Paths group."""

from pathlib import Path

from model.ui_field import UIField


def _named(name: str, field: UIField) -> UIField:
    """Set the name attribute on a UIField and return it."""
    field.name = name
    return field


bind_usr = _named("bind_usr", UIField(
    bool, True, "opt-usr",
    "/usr", "Programs and libraries",
    # bwrap_args handled via bound_dirs sync in Quick Shortcuts
))
bind_usr.shortcut_path = Path("/usr")

bind_bin = _named("bind_bin", UIField(
    bool, True, "opt-bin",
    "/bin", "Essential binaries",
    # bwrap_args handled via bound_dirs sync in Quick Shortcuts
))
bind_bin.shortcut_path = Path("/bin")

bind_lib = _named("bind_lib", UIField(
    bool, True, "opt-lib",
    "/lib", "Shared libraries",
    # bwrap_args handled via bound_dirs sync in Quick Shortcuts
))
bind_lib.shortcut_path = Path("/lib")

bind_lib64 = _named("bind_lib64", UIField(
    bool, True, "opt-lib64",
    "/lib64", "64-bit libraries",
    # bwrap_args handled via bound_dirs sync in Quick Shortcuts
))
bind_lib64.shortcut_path = Path("/lib64")

bind_sbin = _named("bind_sbin", UIField(
    bool, True, "opt-sbin",
    "/sbin", "System binaries",
    # bwrap_args handled via bound_dirs sync in Quick Shortcuts
))
bind_sbin.shortcut_path = Path("/sbin")

bind_etc = _named("bind_etc", UIField(
    bool, False, "opt-etc",
    "/etc", "Config files - use caution",
    # bwrap_args handled via bound_dirs sync in Quick Shortcuts
))
bind_etc.shortcut_path = Path("/etc")
