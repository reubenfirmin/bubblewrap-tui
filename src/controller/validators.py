"""Validation functions for controller sync operations."""

import re

from constants import MAX_UID_GID


def sanitize_input(value: str) -> str:
    """Remove newlines and other control characters from free-form input.

    Single-line Textual Inputs already strip newlines on paste (only the first
    line is kept) and can't have newlines typed into them, so this mainly guards
    against values arriving programmatically (e.g. from a hand-edited profile or
    .env import). Use it for free-form string fields that have no stricter
    format validation. Newlines and carriage returns are removed; tabs become
    spaces.

    Args:
        value: Raw string value

    Returns:
        Sanitized string with control characters removed
    """
    return value.replace("\n", "").replace("\r", "").replace("\t", " ")


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


def validate_hostname(value: str) -> str | None:
    """Validate hostname format per RFC 1123.

    Valid hostnames:
    - 1-63 characters
    - Start and end with alphanumeric
    - May contain hyphens (not at start/end)
    - Case-insensitive (we preserve case)

    Args:
        value: String value from input field

    Returns:
        Stripped hostname or None if invalid format
    """
    stripped = value.strip()
    if not stripped:
        return ""  # Empty is valid (means no custom hostname)

    # RFC 1123: max 63 chars, alphanumeric and hyphens, can't start/end with hyphen
    if len(stripped) > 63:
        return None

    # Must start and end with alphanumeric
    if not re.match(r'^[a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?$', stripped):
        # Allow single-character hostnames
        if len(stripped) == 1 and stripped.isalnum():
            return stripped
        return None

    return stripped


def validate_tmpfs_size(value: str) -> str | None:
    """Validate tmpfs size format.

    Valid formats:
    - Empty string (no size limit)
    - Number with optional suffix: K, M, G (case-insensitive)
    - Examples: "100M", "1G", "512K", "1024"

    Args:
        value: String value from input field

    Returns:
        Stripped size string or None if invalid format
    """
    stripped = value.strip()
    if not stripped:
        return ""  # Empty is valid (means no size limit)

    # Match number with optional K/M/G suffix
    if not re.match(r'^\d+[KMGkmg]?$', stripped):
        return None

    return stripped


def validate_chdir(value: str) -> str:
    """Validate/transform chdir path.

    We only strip whitespace here. Path existence can't be validated
    because:
    - The path might be created by binds
    - The path might only exist inside the sandbox
    - bwrap will report a clear error if the path doesn't exist

    Args:
        value: String value from input field

    Returns:
        Stripped path string
    """
    return sanitize_input(value).strip()


def validate_username(value: str) -> str | None:
    """Validate username format.

    Valid usernames (following POSIX conventions):
    - Start with letter or underscore
    - Contain only letters, digits, underscores, hyphens
    - No control characters, newlines, colons (would corrupt passwd file)

    Args:
        value: String value from input field

    Returns:
        Stripped username or None if invalid format
    """
    stripped = value.strip()
    if not stripped:
        return ""  # Empty is valid (no custom username)

    # POSIX username: starts with letter or underscore, then alphanumeric/underscore/hyphen
    if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_-]*$', stripped):
        return None

    # Additional safety: reject if too long (max 32 chars is common limit)
    if len(stripped) > 32:
        return None

    return stripped
