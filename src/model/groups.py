"""All configuration groups and their instances.

This module defines the complete configuration structure using ConfigGroup
as the fundamental unit. Each group maps to one UI section and one summary bullet.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from model.config import Config
from model.config_group import ConfigGroup

# Import all field definitions from the fields package
from model.fields import (
    # VFS fields
    dev_mode, mount_proc, mount_tmp, tmpfs_size,
    # System path fields
    bind_usr, bind_bin, bind_lib, bind_lib64, bind_sbin, bind_etc,
    # User fields
    unshare_user, synthetic_passwd, overlay_home,
    uid_field, gid_field, username_field,
    # Isolation fields
    unshare_pid, unshare_ipc, unshare_uts, unshare_cgroup, disable_userns,
    # Process fields
    die_with_parent, new_session, as_pid_1, chdir,
    # Network fields
    share_net, bind_resolv_conf, bind_ssl_certs,
    # Desktop fields
    allow_dbus, allow_display, bind_user_config,
    # Environment fields
    clear_env, custom_hostname,
)

# Import serializers
from model.serializers import (
    vfs_to_args, vfs_to_summary,
    network_to_args, network_to_summary,
    desktop_to_args, desktop_to_summary,
    user_to_args, user_to_summary,
    isolation_to_summary,
    hostname_to_summary,
    process_to_args, process_to_summary,
    environment_to_args, environment_to_summary,
)

if TYPE_CHECKING:
    from model.network_filter import NetworkFilter


# =============================================================================
# Color Scheme
# =============================================================================
# Tailwind CSS 400-level palette - designed for dark backgrounds
# Tetradic scheme avoiding blue (app's primary)

COLORS = [
    "#F472B6",  # pink-400 (warm)
    "#FBBF24",  # amber-400 (warm)
    "#34D399",  # emerald-400 (cool)
    "#A78BFA",  # violet-400 (cool)
]
DEFAULT_COLOR = "#6B7280"  # gray-500 (clearly inactive)


# =============================================================================
# Legacy aliases for backwards compatibility
# These are re-exports from the serializers module with underscore prefix
# =============================================================================

_vfs_to_args = vfs_to_args
_vfs_to_summary = vfs_to_summary
_network_to_args = network_to_args
_network_to_summary = network_to_summary
_desktop_to_args = desktop_to_args
_desktop_to_summary = desktop_to_summary
_user_to_args = user_to_args
_user_to_summary = user_to_summary
_isolation_to_summary = isolation_to_summary
_hostname_to_summary = hostname_to_summary
_process_to_args = process_to_args
_process_to_summary = process_to_summary
_environment_to_args = environment_to_args
_environment_to_summary = environment_to_summary


# =============================================================================
# ConfigGroup Instances
# =============================================================================

# --- Filesystem Tab Groups ---

vfs_group = ConfigGroup(
    name="vfs",
    title="Virtual Filesystems",
    items=[dev_mode, mount_proc, mount_tmp, tmpfs_size],
    _to_args_fn=_vfs_to_args,
    _to_summary_fn=_vfs_to_summary,
)

system_paths_group = ConfigGroup(
    name="system_paths",
    title="System Paths (read-only)",
    items=[bind_usr, bind_bin, bind_lib, bind_lib64, bind_sbin, bind_etc],
    # No summary - system paths are shown via bound_dirs
)


# --- Sandbox Tab Groups ---

user_group = ConfigGroup(
    name="user",
    title="User",
    items=[unshare_user, synthetic_passwd, uid_field, gid_field, username_field],
    _to_args_fn=_user_to_args,
    _to_summary_fn=_user_to_summary,
)

isolation_group = ConfigGroup(
    name="isolation",
    title="Isolate",
    items=[unshare_pid, unshare_ipc, unshare_cgroup, disable_userns],
    _to_summary_fn=_isolation_to_summary,
)

hostname_group = ConfigGroup(
    name="hostname",
    title="Hostname",
    items=[unshare_uts, custom_hostname],
    _to_summary_fn=hostname_to_summary,
)

process_group = ConfigGroup(
    name="process",
    title="Process",
    items=[die_with_parent, new_session, as_pid_1, chdir],
)

network_group = ConfigGroup(
    name="network",
    title="Network",
    items=[share_net, bind_resolv_conf, bind_ssl_certs],
    _to_args_fn=_network_to_args,
    _to_summary_fn=_network_to_summary,
)

desktop_group = ConfigGroup(
    name="desktop",
    title="Desktop Integration",
    items=[allow_dbus, allow_display, bind_user_config],  # bind_user_config also in Quick Shortcuts
    _to_args_fn=_desktop_to_args,
    _to_summary_fn=_desktop_to_summary,
)


# --- Environment Tab Group ---

environment_group = ConfigGroup(
    name="env_vars",
    title="Environment Variables",
    items=[clear_env],
    _to_args_fn=_environment_to_args,
    _to_summary_fn=_environment_to_summary,
)
# Initialize data fields
environment_group.set("keep_env_vars", set())
environment_group.set("unset_env_vars", set())
environment_group.set("custom_env_vars", {})


# --- Directories Tab Group (placeholder - uses BoundDirectory list) ---

directories_group = ConfigGroup(
    name="bound_dirs",
    title="Bound Directories",
    items=[],  # Managed separately via BoundDirectory list
)


# --- Overlays Tab Group (placeholder - uses OverlayConfig list) ---

overlays_group = ConfigGroup(
    name="overlays",
    title="Overlays",
    description=(
        "Overlays make directories appear writable without changing originals.\n\n"
        "  tmpfs      Changes discarded on exit\n"
        "  persistent Changes saved to write dir\n\n"
        "Example: source=/usr, mount=/usr, mode=tmpfs\n"
        "         Sandbox can 'install' packages, real /usr untouched."
    ),
    items=[],  # Managed separately via OverlayConfig list
)


# =============================================================================
# Config Instances (one per tab)
# =============================================================================

filesystem_config = Config(
    name="filesystem",
    groups=[vfs_group, system_paths_group],
)

sandbox_config = Config(
    name="sandbox",
    groups=[user_group, isolation_group, hostname_group, process_group, network_group, desktop_group],
)

environment_config = Config(
    name="environment",
    groups=[environment_group],
)

directories_config = Config(
    name="directories",
    groups=[directories_group],
)

overlays_config = Config(
    name="overlays",
    groups=[overlays_group],
)


# =============================================================================
# All Configs and Utilities
# =============================================================================

ALL_CONFIGS = [
    filesystem_config,
    sandbox_config,
    environment_config,
    directories_config,
    overlays_config,
]


def all_groups() -> list[ConfigGroup]:
    """All groups in order for serialization."""
    groups = []
    for config in ALL_CONFIGS:
        groups.extend(config.groups)
    return groups


def get_group(name: str) -> ConfigGroup | None:
    """Get a group by name from all configs."""
    for config in ALL_CONFIGS:
        group = config.get_group(name)
        if group:
            return group
    return None


# Quick shortcuts - UIField objects with shortcut_path attribute
QUICK_SHORTCUTS = [
    bind_usr,
    bind_bin,
    bind_lib,
    bind_lib64,
    bind_sbin,
    bind_etc,
    bind_user_config,
]

# Build checkbox_id -> UIField mapping for quick shortcuts
QUICK_SHORTCUT_BY_CHECKBOX_ID = {
    field.checkbox_id: field for field in QUICK_SHORTCUTS
}
