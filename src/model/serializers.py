"""Custom to_args and to_summary functions for ConfigGroups.

These functions handle complex serialization logic that depends on multiple
fields or requires special processing beyond simple flag mapping.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from model.config_group import ConfigGroup
    from model.network_filter import NetworkFilter


# =============================================================================
# Virtual Filesystems Serializers
# =============================================================================

def vfs_to_args(group: ConfigGroup) -> list[str]:
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


def vfs_to_summary(group: ConfigGroup) -> str | None:
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


# =============================================================================
# Network Serializers
# =============================================================================

def network_to_args(group: ConfigGroup, network_filter: "NetworkFilter | None" = None) -> list[str]:
    """Custom to_args for network (handles DNS/SSL path detection and filtering).

    Args:
        group: The network ConfigGroup
        network_filter: Optional NetworkFilter config for pasta filtering
    """
    from detection import find_dns_paths, find_ssl_cert_paths
    from net import uses_dns_proxy

    args = []

    # Check if network filtering is active (uses pasta)
    filtering_active = network_filter and network_filter.requires_pasta()

    if filtering_active:
        # Network filtering requires isolated network namespace (pasta provides filtered network)
        args.append("--unshare-net")
    elif group.get("share_net"):
        # Full network access
        args.append("--share-net")

    # DNS bindings - skip if DNS proxy is active (proxy creates its own /etc/resolv.conf)
    dns_proxy_active = network_filter and uses_dns_proxy(network_filter)
    if group.get("bind_resolv_conf") and not dns_proxy_active:
        for dns_path in find_dns_paths():
            args.extend(["--ro-bind", dns_path, dns_path])

    # SSL bindings are always needed for both full access and filtered network
    if group.get("bind_ssl_certs"):
        for cert_path in find_ssl_cert_paths():
            args.extend(["--ro-bind", cert_path, cert_path])

    return args


def network_to_summary(group: ConfigGroup) -> str | None:
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


# =============================================================================
# Desktop Integration Serializers
# =============================================================================

def desktop_to_args(group: ConfigGroup) -> list[str]:
    """Custom to_args for desktop integration."""
    from detection import detect_dbus_session, detect_display_server

    args = []
    if group.get("allow_dbus"):
        for dbus_path in detect_dbus_session():
            args.extend(["--bind", dbus_path, dbus_path])

    if group.get("allow_display"):
        display_info = detect_display_server()
        for display_path in display_info.paths:
            args.extend(["--ro-bind", display_path, display_path])

    # Note: bind_user_config is now handled via Quick Shortcuts -> bound_dirs

    return args


def desktop_to_summary(group: ConfigGroup) -> str | None:
    """Custom summary for desktop integration."""
    from detection import detect_display_server

    lines = []

    if group.get("allow_display"):
        display_info = detect_display_server()
        display_type = display_info.type
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


# =============================================================================
# User Identity Serializers
# =============================================================================

def user_to_args(group: ConfigGroup) -> list[str]:
    """Custom to_args for user identity.

    Note: Virtual user (passwd/group generation) is handled separately in bwrap.py
    via FD-based injection. This only handles the basic --unshare-user and --uid/--gid.
    """
    args = []

    if group.get("unshare_user"):
        args.append("--unshare-user")
        args.extend(["--uid", str(group.get("uid"))])
        args.extend(["--gid", str(group.get("gid"))])

    return args


def user_to_summary(group: ConfigGroup) -> str | None:
    """Custom summary for user identity."""
    if not group.get("unshare_user"):
        return None

    lines = []
    uid = group.get("uid")
    gid = group.get("gid")
    username = group.get("username")

    if username and uid > 0:
        lines.append(f"Identity: {username} (UID {uid}, GID {gid}) with generated /etc/passwd")
    else:
        lines.append(f"Identity: Runs as UID {uid}, GID {gid} inside sandbox")

    return "\n".join(lines) if lines else None


# =============================================================================
# Isolation Serializers
# =============================================================================

def isolation_to_summary(group: ConfigGroup, network_filter: "NetworkFilter | None" = None) -> str | None:
    """Custom summary for isolation namespaces.

    Args:
        group: The isolation ConfigGroup
        network_filter: Optional NetworkFilter to detect seccomp auto-enable
    """
    from model.fields.isolation import unshare_pid, unshare_ipc, unshare_cgroup, disable_userns, seccomp_block_userns

    items = []
    # Note: unshare_user is now in user_group, not here
    # Note: unshare_uts is now in hostname_group, not here
    ns_items = [
        ("unshare_pid", unshare_pid),
        ("unshare_ipc", unshare_ipc),
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

    # Check if seccomp will be auto-enabled due to network filtering + disable_userns conflict
    seccomp_auto_enabled = (
        network_filter is not None
        and network_filter.requires_pasta()
        and group.get("disable_userns")
        and not group.get("seccomp_block_userns")
    )

    # Handle nested sandboxing blocking
    if group.get("seccomp_block_userns"):
        lines.append(f"Nested sandboxing: DISABLED via seccomp — {seccomp_block_userns.summary}")
    elif seccomp_auto_enabled:
        lines.append(f"Nested sandboxing: DISABLED via seccomp (auto-enabled for network filtering compatibility)")
        lines.append("  WARNING: Using seccomp filter instead of bwrap's --disable-userns")
    elif group.get("disable_userns"):
        lines.append(f"Nested sandboxing: DISABLED — {disable_userns.summary}")

    return "\n".join(lines) if lines else None


# =============================================================================
# Hostname Serializers
# =============================================================================

def hostname_to_summary(group: ConfigGroup) -> str | None:
    """Custom summary for hostname configuration."""
    lines = []

    if group.get("unshare_uts"):
        custom = group.get("custom_hostname")
        if custom:
            lines.append(f"Hostname: '{custom}' — isolated from host")
        else:
            lines.append("Hostname: Isolated — gets random hostname, cannot see host's")

    return "\n".join(lines) if lines else None


# =============================================================================
# Process Serializers
# =============================================================================

def process_to_args(group: ConfigGroup, isolation_group: ConfigGroup) -> list[str]:
    """Custom to_args for process (needs isolation group for PID namespace check)."""
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

    # Note: uid/gid handling moved to user_group

    return args


def process_to_summary(group: ConfigGroup, env_group: ConfigGroup) -> str | None:
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

    # Note: Identity summary moved to user_group
    # Note: Hostname summary moved to hostname_group

    return "\n".join(lines) if lines else None


# =============================================================================
# Environment Serializers
# =============================================================================

def environment_to_args(group: ConfigGroup) -> list[str]:
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

    return args


def environment_to_summary(group: ConfigGroup) -> str | None:
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
