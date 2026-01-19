"""All configuration groups and their instances.

This module defines the complete configuration structure using ConfigGroup
as the fundamental unit. Each group maps to one UI section and one summary bullet.
"""

from __future__ import annotations

import os
from pathlib import Path

from model.config import Config
from model.config_group import ConfigGroup
from model.ui_field import UIField, Field


def _named(name: str, field: UIField) -> UIField:
    """Set the name attribute on a UIField and return it."""
    field.name = name
    return field

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
# UIField Definitions - Virtual Filesystems Group
# =============================================================================

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


# =============================================================================
# UIField Definitions - System Paths Group
# =============================================================================

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


# =============================================================================
# UIField Definitions - Isolation Group (Namespaces)
# =============================================================================

unshare_user = _named("unshare_user", UIField(
    bool, False, "opt-unshare-user",
    "User namespace", "Appear as different user inside",
    bwrap_flag="--unshare-user",
    summary="Isolated user IDs — sandbox sees different UID/GID than host",
))

unshare_pid = _named("unshare_pid", UIField(
    bool, False, "opt-unshare-pid",
    "PID namespace", "Hide host processes",
    bwrap_flag="--unshare-pid",
    summary="Cannot see or signal host processes",
))

unshare_ipc = _named("unshare_ipc", UIField(
    bool, False, "opt-unshare-ipc",
    "IPC namespace", "Isolated shared memory",
    bwrap_flag="--unshare-ipc",
    summary="Cannot access host shared memory or semaphores",
))

unshare_uts = _named("unshare_uts", UIField(
    bool, False, "opt-unshare-uts",
    "UTS namespace", "Own hostname inside",
    bwrap_flag="--unshare-uts",
    summary="Isolated hostname — cannot see or modify host's hostname",
))

unshare_cgroup = _named("unshare_cgroup", UIField(
    bool, False, "opt-unshare-cgroup",
    "Cgroup namespace", "Isolated resource limits",
    bwrap_flag="--unshare-cgroup",
    summary="Isolated cgroup view — sees only its own resource accounting",
))

disable_userns = _named("disable_userns", UIField(
    bool, False, "opt-disable-userns",
    "Disable nested sandboxing", "Prevent user namespaces inside",
    bwrap_flag="--disable-userns",
    summary="Cannot create nested containers — prevents namespace escape attacks",
))


# =============================================================================
# UIField Definitions - Process Group
# =============================================================================

die_with_parent = _named("die_with_parent", UIField(
    bool, True, "opt-die-with-parent",
    "Kill with parent", "Dies when terminal closes",
    bwrap_flag="--die-with-parent",
))

new_session = _named("new_session", UIField(
    bool, True, "opt-new-session",
    "New session", "Prevents terminal escape attacks, but disables job control",
    bwrap_flag="--new-session",
))

as_pid_1 = _named("as_pid_1", UIField(
    bool, False, "opt-as-pid-1",
    "Run as PID 1", "Command runs as init process in PID namespace",
    bwrap_flag="--as-pid-1",
))

chdir = _named("chdir", UIField(
    str, "", "opt-chdir",
    "Working dir", "Directory to start in",
    bwrap_args=lambda v: ["--chdir", v] if v else [],
))

# UID/GID fields (data fields, not standard checkboxes)
uid_field = Field(int, default_factory=os.getuid)
gid_field = Field(int, default_factory=os.getgid)


# =============================================================================
# UIField Definitions - Network Group
# =============================================================================

share_net = _named("share_net", UIField(
    bool, False, "opt-net",
    "Allow network", "Enable host network access",
    bwrap_flag="--share-net",
))

bind_resolv_conf = _named("bind_resolv_conf", UIField(
    bool, False, "opt-resolv-conf",
    "DNS config", "/etc/resolv.conf for hostname resolution",
    # bwrap_args handled by group's custom to_args
))

bind_ssl_certs = _named("bind_ssl_certs", UIField(
    bool, False, "opt-ssl-certs",
    "SSL certificates", "/etc/ssl/certs for HTTPS",
    # bwrap_args handled by group's custom to_args
))


# =============================================================================
# UIField Definitions - Desktop Group
# =============================================================================

allow_dbus = _named("allow_dbus", UIField(
    bool, False, "opt-dbus",
    "D-Bus session", "Open browser, notifications, etc.",
    # bwrap_args handled by group's custom to_args
))

allow_display = _named("allow_display", UIField(
    bool, False, "opt-display",
    "Display server", "X11/Wayland display access",
    # bwrap_args handled by group's custom to_args
))

bind_user_config = _named("bind_user_config", UIField(
    bool, False, "opt-user-config",
    "~/.config", "App settings - use caution",
    # bwrap_args handled via bound_dirs sync in Quick Shortcuts
))
bind_user_config.shortcut_path = Path.home() / ".config"


# =============================================================================
# UIField Definitions - Environment Group
# =============================================================================

clear_env = _named("clear_env", UIField(
    bool, False, "toggle-clear-btn",
    "Clear environment", "Start with empty environment",
    bwrap_flag="--clearenv",
))

custom_hostname = _named("custom_hostname", UIField(
    str, "", "opt-hostname",
    "Custom hostname", "Hostname inside the sandbox",
    bwrap_args=lambda v: ["--hostname", v] if v else [],
))

# Data fields for environment
keep_env_vars_field = Field(set, default_factory=set)
unset_env_vars_field = Field(set, default_factory=set)
custom_env_vars_field = Field(dict, default_factory=dict)


# =============================================================================
# Custom to_args functions for groups with special logic
# =============================================================================

def _vfs_to_args(group: ConfigGroup) -> list[str]:
    """Custom to_args for virtual filesystems (handles /tmp + size)."""
    args = []

    # /dev mode
    dev_mode_val = group.get("dev_mode")
    if dev_mode_val == "minimal":
        args.extend(["--dev", "/dev"])
    elif dev_mode_val == "full":
        args.extend(["--bind", "/dev", "/dev"])

    # /proc
    if group.get("mount_proc"):
        args.extend(["--proc", "/proc"])

    # /tmp with optional size
    if group.get("mount_tmp"):
        size = group.get("tmpfs_size")
        if size:
            args.extend(["--size", size, "--tmpfs", "/tmp"])
        else:
            args.extend(["--tmpfs", "/tmp"])

    return args


def _vfs_to_summary(group: ConfigGroup) -> str | None:
    """Custom summary for virtual filesystems."""
    lines = []
    dev_mode_val = group.get("dev_mode")
    if dev_mode_val == "minimal":
        lines.append("/dev: Basic device nodes (null, zero, random, tty) — no real hardware access")
    elif dev_mode_val == "full":
        lines.append("/dev: Full host device access including GPU, USB, and other hardware")

    if group.get("mount_proc"):
        lines.append("/proc: New process filesystem — with PID isolation, only sandbox processes visible")

    if group.get("mount_tmp"):
        size = group.get("tmpfs_size")
        if size:
            lines.append(f"/tmp: Temporary filesystem ({size} max) — files discarded on exit")
        else:
            lines.append("/tmp: Temporary filesystem — files discarded on exit")

    return "\n".join(lines) if lines else None


# Note: _system_paths_to_summary removed - system paths are now shown via bound_dirs summary


def _network_to_args(group: ConfigGroup) -> list[str]:
    """Custom to_args for network (handles DNS/SSL path detection)."""
    from detection import find_dns_paths, find_ssl_cert_paths

    args = []
    if group.get("share_net"):
        args.append("--share-net")

    if group.get("bind_resolv_conf"):
        for dns_path in find_dns_paths():
            args.extend(["--ro-bind", dns_path, dns_path])

    if group.get("bind_ssl_certs"):
        for cert_path in find_ssl_cert_paths():
            args.extend(["--ro-bind", cert_path, cert_path])

    return args


def _network_to_summary(group: ConfigGroup) -> str | None:
    """Custom summary for network."""
    if group.get("share_net"):
        extras = []
        if group.get("bind_resolv_conf"):
            extras.append("DNS config")
        if group.get("bind_ssl_certs"):
            extras.append("SSL certs")
        if extras:
            return f"Network: Full access — can reach internet and local services ({', '.join(extras)} bound)"
        return "Network: Full access — WARNING: missing DNS/SSL, connections may fail"
    return "Network: Completely offline — no network access at all"


def _desktop_to_args(group: ConfigGroup) -> list[str]:
    """Custom to_args for desktop integration."""
    from detection import detect_dbus_session, detect_display_server

    args = []
    if group.get("allow_dbus"):
        for dbus_path in detect_dbus_session():
            args.extend(["--bind", dbus_path, dbus_path])

    if group.get("allow_display"):
        display_info = detect_display_server()
        for display_path in display_info["paths"]:
            args.extend(["--ro-bind", display_path, display_path])

    # Note: bind_user_config is now handled via Quick Shortcuts -> bound_dirs

    return args


def _desktop_to_summary(group: ConfigGroup) -> str | None:
    """Custom summary for desktop integration."""
    from detection import detect_display_server

    lines = []

    if group.get("allow_display"):
        display_info = detect_display_server()
        display_type = display_info["type"]
        if display_type == "x11":
            lines.append("Display: X11 — WARNING: X11 provides NO isolation, sandbox can keylog other apps")
        elif display_type == "wayland":
            lines.append("Display: Wayland — apps isolated from each other (more secure than X11)")
        elif display_type:
            lines.append(f"Display: {display_type.upper()}")

    if group.get("allow_dbus"):
        lines.append("D-Bus: Session bus access — can call host services (systemd, portals, etc.)")

    # Note: bind_user_config is now shown via Quick Shortcuts in directories tab

    return "\n".join(lines) if lines else None


def _isolation_to_summary(group: ConfigGroup) -> str | None:
    """Custom summary for isolation namespaces."""
    items = []
    ns_items = [
        ("unshare_user", unshare_user),
        ("unshare_pid", unshare_pid),
        ("unshare_ipc", unshare_ipc),
        ("unshare_uts", unshare_uts),
        ("unshare_cgroup", unshare_cgroup),
    ]
    for name, field in ns_items:
        if group.get(name):
            items.append(field.summary)

    lines = []
    if items:
        lines.append("Namespace isolation:")
        for item in items:
            lines.append(f"  - {item}")

    # Handle disable_userns separately (important security feature)
    if group.get("disable_userns"):
        lines.append(f"Nested sandboxing: DISABLED — {disable_userns.summary}")

    return "\n".join(lines) if lines else None


def _process_to_args(group: ConfigGroup, isolation_group: ConfigGroup) -> list[str]:
    """Custom to_args for process (needs isolation group for user namespace)."""
    args = []

    if group.get("die_with_parent"):
        args.append("--die-with-parent")

    if group.get("new_session"):
        args.append("--new-session")

    if group.get("as_pid_1"):
        # --as-pid-1 requires --unshare-pid
        if not isolation_group.get("unshare_pid"):
            args.append("--unshare-pid")
        args.append("--as-pid-1")

    chdir_val = group.get("chdir")
    if chdir_val:
        args.extend(["--chdir", chdir_val])

    # User/group mapping (when using user namespace)
    if isolation_group.get("unshare_user"):
        args.extend(["--uid", str(group.get("uid"))])
        args.extend(["--gid", str(group.get("gid"))])

    return args


def _process_to_summary(group: ConfigGroup, isolation_group: ConfigGroup, env_group: ConfigGroup) -> str | None:
    """Custom summary for process behavior."""
    lines = []

    if group.get("die_with_parent"):
        lines.append("Lifecycle: Killed if launcher exits — prevents orphaned sandboxes")

    if group.get("new_session"):
        lines.append("Session: New terminal session — prevents keystroke injection (CVE-2017-5226)")

    if group.get("as_pid_1"):
        lines.append("PID 1: App handles zombie process cleanup itself (advanced)")

    chdir_val = group.get("chdir")
    if chdir_val:
        lines.append(f"Working dir: Starts in {chdir_val}")

    hostname = env_group.get("custom_hostname")
    if hostname:
        lines.append(f"Hostname: {hostname}")

    if isolation_group.get("unshare_user"):
        lines.append(f"Identity: Runs as UID {group.get('uid')}, GID {group.get('gid')} inside sandbox")

    return "\n".join(lines) if lines else None


def _environment_to_args(group: ConfigGroup) -> list[str]:
    """Custom to_args for environment variables."""
    args = []

    if group.get("clear_env"):
        args.append("--clearenv")
        # Re-set kept vars
        keep_vars = group.get("keep_env_vars") or set()
        for var in keep_vars:
            if var in os.environ:
                args.extend(["--setenv", var, os.environ[var]])
    else:
        # Unset specific vars
        unset_vars = group.get("unset_env_vars") or set()
        for var in unset_vars:
            args.extend(["--unsetenv", var])

    # Custom env vars
    custom_vars = group.get("custom_env_vars") or {}
    for name, value in custom_vars.items():
        args.extend(["--setenv", name, value])

    # Hostname
    hostname = group.get("custom_hostname")
    if hostname:
        args.extend(["--hostname", hostname])

    return args


def _environment_to_summary(group: ConfigGroup) -> str | None:
    """Custom summary for environment."""
    lines = []
    keep_vars = group.get("keep_env_vars") or set()
    custom_vars = group.get("custom_env_vars") or {}

    if group.get("clear_env"):
        if keep_vars:
            lines.append(f"Environment: CLEARED, passing through {len(keep_vars)} vars from parent")
        else:
            lines.append("Environment: CLEARED — secrets like API keys won't leak to sandbox")
    else:
        unset_vars = group.get("unset_env_vars") or set()
        if unset_vars:
            lines.append(f"Environment: Inherited minus {len(unset_vars)} removed vars")
        else:
            lines.append("Environment: Fully inherited — sandbox sees all parent env vars including secrets")

    if custom_vars:
        lines.append(f"Custom vars set: {', '.join(custom_vars.keys())}")

    return "\n".join(lines) if lines else None


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

isolation_group = ConfigGroup(
    name="isolation",
    title="Isolation",
    items=[unshare_user, unshare_pid, unshare_ipc, unshare_uts, unshare_cgroup, disable_userns],
    _to_summary_fn=_isolation_to_summary,
)

process_group = ConfigGroup(
    name="process",
    title="Process",
    items=[die_with_parent, new_session, as_pid_1, chdir],
)
# Initialize uid/gid with factory values
process_group.set("uid", os.getuid())
process_group.set("gid", os.getgid())

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
    items=[clear_env, custom_hostname],
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
    groups=[isolation_group, process_group, network_group, desktop_group],
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
