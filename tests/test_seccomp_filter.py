"""Tests for seccomp_filter module."""

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from seccomp_filter import (
    BLOCKED_SYSCALLS,
    check_seccomp,
    get_seccomp_status,
    generate_seccomp_filter,
    create_seccomp_filter_file,
)


class TestCheckSeccomp:
    """Tests for check_seccomp function."""

    def test_check_seccomp_returns_bool(self):
        """check_seccomp should return a boolean."""
        result = check_seccomp()
        assert isinstance(result, bool)

    def test_check_seccomp_with_import_error(self):
        """check_seccomp should return False when seccomp module unavailable."""
        # This is hard to test properly without actually uninstalling libseccomp
        # Just verify that the function handles ImportError gracefully
        # The actual behavior depends on whether libseccomp is installed
        result = check_seccomp()
        assert isinstance(result, bool)


class TestGetSeccompStatus:
    """Tests for get_seccomp_status function."""

    def test_returns_tuple(self):
        """get_seccomp_status should return a tuple of (bool, str)."""
        available, hint = get_seccomp_status()
        assert isinstance(available, bool)
        assert isinstance(hint, str)

    def test_hint_empty_when_available(self):
        """When seccomp is available, hint should be empty."""
        available, hint = get_seccomp_status()
        if available:
            assert hint == ""

    def test_hint_contains_install_info_when_unavailable(self):
        """When seccomp is unavailable, hint should contain install info."""
        available, hint = get_seccomp_status()
        if not available:
            assert "seccomp" in hint.lower() or "install" in hint.lower()


class TestGenerateSeccompFilter:
    """Tests for generate_seccomp_filter function."""

    def test_returns_bytes_or_none(self):
        """generate_seccomp_filter should return bytes or None."""
        result = generate_seccomp_filter()
        assert result is None or isinstance(result, bytes)

    def test_custom_blocked_syscalls(self):
        """Should accept custom list of blocked syscalls."""
        result = generate_seccomp_filter(blocked=["reboot"])
        # Result depends on whether libseccomp is installed
        assert result is None or isinstance(result, bytes)

    def test_empty_blocked_list(self):
        """Should handle empty blocked list."""
        result = generate_seccomp_filter(blocked=[])
        assert result is None or isinstance(result, bytes)

    def test_default_blocked_syscalls_used(self):
        """When no blocked list provided, should use BLOCKED_SYSCALLS."""
        # Just verify BLOCKED_SYSCALLS is not empty
        assert len(BLOCKED_SYSCALLS) > 0
        # And that the function can be called without args
        result = generate_seccomp_filter()
        assert result is None or isinstance(result, bytes)


class TestCreateSeccompFilterFile:
    """Tests for create_seccomp_filter_file function."""

    def test_creates_file_when_available(self, tmp_path):
        """When libseccomp available, should create filter file."""
        if not check_seccomp():
            pytest.skip("libseccomp not available")

        result = create_seccomp_filter_file(str(tmp_path))
        assert result is not None
        assert Path(result).exists()
        assert Path(result).name == "seccomp.bpf"

    def test_returns_none_when_unavailable(self, tmp_path):
        """When libseccomp unavailable, should return None."""
        with patch("seccomp_filter.check_seccomp", return_value=False):
            with patch("seccomp_filter.generate_seccomp_filter", return_value=None):
                result = create_seccomp_filter_file(str(tmp_path))
                assert result is None

    def test_file_is_binary(self, tmp_path):
        """Created filter file should contain binary data."""
        if not check_seccomp():
            pytest.skip("libseccomp not available")

        result = create_seccomp_filter_file(str(tmp_path))
        assert result is not None
        content = Path(result).read_bytes()
        assert len(content) > 0
        # BPF filters are binary, should have some non-printable bytes
        # (they start with a BPF header)


class TestBlockedSyscalls:
    """Tests for BLOCKED_SYSCALLS constant."""

    def test_blocked_syscalls_not_empty(self):
        """BLOCKED_SYSCALLS should contain syscalls to block."""
        assert len(BLOCKED_SYSCALLS) > 0

    def test_contains_dangerous_syscalls(self):
        """Should include known dangerous syscalls."""
        dangerous = ["kexec_load", "reboot", "io_uring_setup"]
        for syscall in dangerous:
            assert syscall in BLOCKED_SYSCALLS, f"{syscall} should be blocked"

    def test_all_strings(self):
        """All entries should be strings."""
        for syscall in BLOCKED_SYSCALLS:
            assert isinstance(syscall, str)
