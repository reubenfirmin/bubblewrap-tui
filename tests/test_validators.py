"""Tests for controller validators."""

import pytest

from controller.validators import (
    validate_chdir,
    validate_hostname,
    validate_tmpfs_size,
    validate_uid_gid,
    validate_username,
)


class TestValidateUidGid:
    """Tests for validate_uid_gid function."""

    def test_valid_zero(self):
        """Zero is valid (root)."""
        assert validate_uid_gid("0") == 0

    def test_valid_typical_uid(self):
        """Typical user UID is valid."""
        assert validate_uid_gid("1000") == 1000

    def test_valid_max_uid(self):
        """Maximum UID (65535) is valid."""
        assert validate_uid_gid("65535") == 65535

    def test_invalid_negative(self):
        """Negative numbers are invalid."""
        assert validate_uid_gid("-1") is None

    def test_invalid_too_large(self):
        """UIDs over 65535 are invalid."""
        assert validate_uid_gid("65536") is None

    def test_invalid_non_numeric(self):
        """Non-numeric strings are invalid."""
        assert validate_uid_gid("abc") is None

    def test_strips_whitespace(self):
        """Whitespace is stripped."""
        assert validate_uid_gid("  1000  ") == 1000


class TestValidateHostname:
    """Tests for validate_hostname function."""

    def test_empty_is_valid(self):
        """Empty string is valid (no custom hostname)."""
        assert validate_hostname("") == ""

    def test_simple_hostname(self):
        """Simple alphanumeric hostname is valid."""
        assert validate_hostname("sandbox") == "sandbox"

    def test_hostname_with_hyphens(self):
        """Hostname with hyphens is valid."""
        assert validate_hostname("my-sandbox") == "my-sandbox"

    def test_hostname_with_numbers(self):
        """Hostname with numbers is valid."""
        assert validate_hostname("sandbox123") == "sandbox123"

    def test_single_char_hostname(self):
        """Single character hostname is valid."""
        assert validate_hostname("a") == "a"

    def test_max_length_hostname(self):
        """63-character hostname is valid."""
        hostname = "a" * 63
        assert validate_hostname(hostname) == hostname

    def test_too_long_hostname(self):
        """64+ character hostname is invalid."""
        hostname = "a" * 64
        assert validate_hostname(hostname) is None

    def test_hyphen_at_start_invalid(self):
        """Hostname starting with hyphen is invalid."""
        assert validate_hostname("-sandbox") is None

    def test_hyphen_at_end_invalid(self):
        """Hostname ending with hyphen is invalid."""
        assert validate_hostname("sandbox-") is None

    def test_special_chars_invalid(self):
        """Hostname with special characters is invalid."""
        assert validate_hostname("sand_box") is None
        assert validate_hostname("sand.box") is None
        assert validate_hostname("sand@box") is None

    def test_strips_whitespace(self):
        """Whitespace is stripped."""
        assert validate_hostname("  sandbox  ") == "sandbox"


class TestValidateTmpfsSize:
    """Tests for validate_tmpfs_size function."""

    def test_empty_is_valid(self):
        """Empty string is valid (no size limit)."""
        assert validate_tmpfs_size("") == ""

    def test_plain_number(self):
        """Plain number (bytes) is valid."""
        assert validate_tmpfs_size("1024") == "1024"

    def test_kilobytes(self):
        """Number with K suffix is valid."""
        assert validate_tmpfs_size("512K") == "512K"
        assert validate_tmpfs_size("512k") == "512k"

    def test_megabytes(self):
        """Number with M suffix is valid."""
        assert validate_tmpfs_size("100M") == "100M"
        assert validate_tmpfs_size("100m") == "100m"

    def test_gigabytes(self):
        """Number with G suffix is valid."""
        assert validate_tmpfs_size("1G") == "1G"
        assert validate_tmpfs_size("1g") == "1g"

    def test_invalid_suffix(self):
        """Invalid suffix is rejected."""
        assert validate_tmpfs_size("100T") is None
        assert validate_tmpfs_size("100B") is None

    def test_invalid_format(self):
        """Invalid formats are rejected."""
        assert validate_tmpfs_size("abc") is None
        assert validate_tmpfs_size("100 M") is None
        assert validate_tmpfs_size("M100") is None

    def test_strips_whitespace(self):
        """Whitespace is stripped."""
        assert validate_tmpfs_size("  100M  ") == "100M"


class TestValidateChdir:
    """Tests for validate_chdir function."""

    def test_empty_is_valid(self):
        """Empty string is valid."""
        assert validate_chdir("") == ""

    def test_absolute_path(self):
        """Absolute path is valid."""
        assert validate_chdir("/home/user") == "/home/user"

    def test_relative_path(self):
        """Relative path is valid (bwrap handles it)."""
        assert validate_chdir("subdir") == "subdir"

    def test_strips_whitespace(self):
        """Whitespace is stripped."""
        assert validate_chdir("  /home/user  ") == "/home/user"


class TestValidateUsername:
    """Tests for validate_username function."""

    def test_empty_is_valid(self):
        """Empty string is valid (no custom username)."""
        assert validate_username("") == ""

    def test_simple_username(self):
        """Simple alphanumeric username is valid."""
        assert validate_username("john") == "john"

    def test_username_with_underscore(self):
        """Username starting with underscore is valid."""
        assert validate_username("_system") == "_system"

    def test_username_with_hyphen(self):
        """Username with hyphens is valid."""
        assert validate_username("john-doe") == "john-doe"

    def test_username_with_numbers(self):
        """Username with numbers is valid."""
        assert validate_username("user123") == "user123"

    def test_max_length_username(self):
        """32-character username is valid."""
        username = "a" * 32
        assert validate_username(username) == username

    def test_too_long_username(self):
        """33+ character username is invalid."""
        username = "a" * 33
        assert validate_username(username) is None

    def test_starts_with_number_invalid(self):
        """Username starting with number is invalid."""
        assert validate_username("1user") is None

    def test_starts_with_hyphen_invalid(self):
        """Username starting with hyphen is invalid."""
        assert validate_username("-user") is None

    def test_newline_invalid(self):
        """Username with newline is invalid (security issue)."""
        assert validate_username("user\nroot") is None

    def test_control_char_invalid(self):
        """Username with control characters is invalid."""
        assert validate_username("user\x00root") is None

    def test_colon_invalid(self):
        """Username with colon is invalid (would corrupt passwd)."""
        assert validate_username("user:root") is None

    def test_special_chars_invalid(self):
        """Username with special characters is invalid."""
        assert validate_username("user@host") is None
        assert validate_username("user.name") is None
        assert validate_username("user name") is None

    def test_strips_whitespace(self):
        """Whitespace is stripped."""
        assert validate_username("  john  ") == "john"
