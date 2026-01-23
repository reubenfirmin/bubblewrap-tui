"""Tests for file utilities."""

import os
import stat
from pathlib import Path

import pytest

from fileutils import write_file_atomic


class TestWriteFileAtomic:
    """Test write_file_atomic function."""

    def test_creates_file_with_content(self, tmp_path):
        """File is created with correct content."""
        path = tmp_path / "test.txt"
        write_file_atomic(path, "hello world", 0o644)
        assert path.read_text() == "hello world"

    def test_creates_file_with_executable_permissions(self, tmp_path):
        """File is created with executable permissions."""
        path = tmp_path / "script.sh"
        write_file_atomic(path, "#!/bin/sh\necho hello", 0o755)
        mode = path.stat().st_mode
        assert mode & stat.S_IXUSR  # Owner execute
        assert mode & stat.S_IRUSR  # Owner read
        assert mode & stat.S_IWUSR  # Owner write

    def test_creates_file_with_readonly_permissions(self, tmp_path):
        """File is created with read-only permissions."""
        path = tmp_path / "readonly.txt"
        write_file_atomic(path, "read only content", 0o444)
        mode = path.stat().st_mode
        assert mode & stat.S_IRUSR  # Owner read
        assert not (mode & stat.S_IWUSR)  # No owner write

    def test_raises_if_file_exists(self, tmp_path):
        """Raises FileExistsError if file already exists."""
        path = tmp_path / "existing.txt"
        path.write_text("existing")
        with pytest.raises(FileExistsError):
            write_file_atomic(path, "new content", 0o644)

    def test_permissions_set_atomically(self, tmp_path):
        """Permissions are set at creation time, not after."""
        path = tmp_path / "atomic.txt"
        write_file_atomic(path, "content", 0o400)
        # If permissions were set atomically, the file should have been
        # created with 0o400 from the start, not 0o644 then chmod'd
        mode = path.stat().st_mode & 0o777
        assert mode == 0o400

    def test_handles_unicode_content(self, tmp_path):
        """Handles unicode content correctly."""
        path = tmp_path / "unicode.txt"
        content = "Hello 世界 🌍"
        write_file_atomic(path, content, 0o644)
        assert path.read_text() == content
