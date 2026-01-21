"""UIField definitions for User group."""

from model.ui_field import UIField, Field


def _named(name: str, field: UIField) -> UIField:
    """Set the name attribute on a UIField and return it."""
    field.name = name
    return field


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

# UID/GID/Username fields (data fields, not standard checkboxes)
# Default to 0 (root inside sandbox) since that's the common use case
uid_field = Field(int, default=0)
gid_field = Field(int, default=0)
username_field = Field(str, default="")
