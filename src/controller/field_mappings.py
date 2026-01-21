"""Field mapping registry for UI ↔ Config synchronization."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from textual.widgets import Checkbox, Input

from controller.validators import validate_uid_gid
import ui.ids as ids


@dataclass
class FieldMapping:
    """Maps a UI widget to a config field."""

    widget_id: str
    config_path: str  # e.g., "filesystem.mount_proc"
    widget_type: type  # Checkbox or Input
    value_transform: Callable[[Any], Any] | None = None  # Transform UI value to config value
    inverse_transform: Callable[[Any], Any] | None = None  # Transform config value to UI value


# Registry of all checkbox/input mappings
# These map widget IDs to config paths for automatic sync
FIELD_MAPPINGS: list[FieldMapping] = [
    # Filesystem options (Virtual Filesystems)
    FieldMapping(ids.OPT_PROC, "filesystem.mount_proc", Checkbox),
    FieldMapping(ids.OPT_TMP, "filesystem.mount_tmp", Checkbox),
    FieldMapping(ids.OPT_TMPFS_SIZE, "filesystem.tmpfs_size", Input, lambda v: v.strip()),

    # Quick Shortcuts (system paths + user config)
    # These sync checkbox state for profile saving/loading
    # The bound_dirs sync is handled separately in app.py
    FieldMapping(ids.OPT_USR, "filesystem.bind_usr", Checkbox),
    FieldMapping(ids.OPT_BIN, "filesystem.bind_bin", Checkbox),
    FieldMapping(ids.OPT_LIB, "filesystem.bind_lib", Checkbox),
    FieldMapping(ids.OPT_LIB64, "filesystem.bind_lib64", Checkbox),
    FieldMapping(ids.OPT_SBIN, "filesystem.bind_sbin", Checkbox),
    FieldMapping(ids.OPT_ETC, "filesystem.bind_etc", Checkbox),
    FieldMapping(ids.OPT_USER_CONFIG, "desktop.bind_user_config", Checkbox),

    # Network options
    FieldMapping(ids.OPT_NET, "network.share_net", Checkbox),
    FieldMapping(ids.OPT_RESOLV_CONF, "network.bind_resolv_conf", Checkbox),
    FieldMapping(ids.OPT_SSL_CERTS, "network.bind_ssl_certs", Checkbox),

    # Desktop integration
    FieldMapping(ids.OPT_DBUS, "desktop.allow_dbus", Checkbox),
    FieldMapping(ids.OPT_DISPLAY, "desktop.allow_display", Checkbox),
    # Note: bind_user_config is handled via Quick Shortcuts in directories tab

    # User identity (unshare_user, uid, gid, username, synthetic_passwd)
    FieldMapping(ids.OPT_UNSHARE_USER, "user.unshare_user", Checkbox),
    FieldMapping(ids.OPT_UID, "user.uid", Input, validate_uid_gid),
    FieldMapping(ids.OPT_GID, "user.gid", Input, validate_uid_gid),
    FieldMapping(ids.OPT_USERNAME, "user.username", Input, lambda v: v.strip()),
    FieldMapping(ids.OPT_SYNTHETIC_PASSWD, "user.synthetic_passwd", Checkbox),
    # Note: overlay_home is UI-only (like directory shortcuts) - not synced to model

    # Namespaces (PID, IPC, UTS, cgroup)
    FieldMapping(ids.OPT_UNSHARE_PID, "namespace.unshare_pid", Checkbox),
    FieldMapping(ids.OPT_UNSHARE_IPC, "namespace.unshare_ipc", Checkbox),
    FieldMapping(ids.OPT_UNSHARE_UTS, "namespace.unshare_uts", Checkbox),
    FieldMapping(ids.OPT_UNSHARE_CGROUP, "namespace.unshare_cgroup", Checkbox),
    FieldMapping(ids.OPT_DISABLE_USERNS, "namespace.disable_userns", Checkbox),

    # Process options
    FieldMapping(ids.OPT_DIE_WITH_PARENT, "process.die_with_parent", Checkbox),
    FieldMapping(ids.OPT_NEW_SESSION, "process.new_session", Checkbox),
    FieldMapping(ids.OPT_AS_PID_1, "process.as_pid_1", Checkbox),
    FieldMapping(ids.OPT_CHDIR, "process.chdir", Input),
    FieldMapping(ids.OPT_HOSTNAME, "hostname.custom_hostname", Input),
]
