"""UIField definitions for User group."""

from model.ui_field import UIField, Field


def _named(name: str, field: UIField) -> UIField:
    """Set the name attribute on a UIField and return it."""
    field.name = name
    return field


def _validate_uid_gid(value: str) -> int | None:
    """Lazy import wrapper for validate_uid_gid to avoid circular imports."""
    from controller.validators import validate_uid_gid
    return validate_uid_gid(value)


def _validate_username(value: str) -> str | None:
    """Lazy import wrapper for validate_username to avoid circular imports."""
    from controller.validators import validate_username
    return validate_username(value)


unshare_user = _named("unshare_user", UIField(
    bool, False, "opt-unshare-user",
    "Mask user identity", "Appear as different user inside sandbox",
    bwrap_flag="--unshare-user",
    summary="Isolated user IDs — sandbox sees different UID/GID than host",
))

# Virtual user options (shown when unshare_user is enabled)
# synthetic_passwd is in the model - controls passwd/group generation
synthetic_passwd = _named("synthetic_passwd", UIField(
    bool, True, "opt-synthetic-passwd",
    "Synthetic /etc/passwd", "Generate passwd/group for virtual user",
))

# overlay_home is UI-only (like directory shortcuts) - adds/removes from overlays list
# Note: The label "Overlay home directory" is generic; the actual label is updated
# at runtime by _update_home_overlay_label() based on uid/username (e.g., "/root" or "/home/user")
overlay_home = _named("overlay_home", UIField(
    bool, False, "opt-overlay-home",
    "Overlay home directory", "Ephemeral home directory",
))

# UID/GID/Username fields (Input fields with validation)
# Default to 0 (root inside sandbox) since that's the common use case
uid_field = _named("uid", UIField(
    int, 0, "opt-uid",
    "UID", "User ID inside sandbox (0 = root)",
    value_transform=_validate_uid_gid,
))

gid_field = _named("gid", UIField(
    int, 0, "opt-gid",
    "GID", "Group ID inside sandbox",
    value_transform=_validate_uid_gid,
))

username_field = _named("username", UIField(
    str, "", "opt-username",
    "Username", "Username inside sandbox",
    value_transform=_validate_username,
))
