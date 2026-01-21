"""Validation functions for controller sync operations."""

from constants import MAX_UID_GID


def validate_uid_gid(value: str) -> int | None:
    """Validate UID/GID is numeric and in valid range (0-65535).

    Args:
        value: String value from input field

    Returns:
        Validated integer or None if invalid
    """
    stripped = value.strip()
    if not stripped.isdigit():
        return None
    num = int(stripped)
    return num if 0 <= num <= MAX_UID_GID else None
