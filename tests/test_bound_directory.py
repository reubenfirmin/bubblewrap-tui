"""Tests for BoundDirectory model."""

from pathlib import Path

import pytest

from model import BoundDirectory


class TestBoundDirectory:
    """Test BoundDirectory dataclass."""

    def test_create_readonly(self):
        """Create a readonly bound directory."""
        bd = BoundDirectory(path=Path("/home/user/docs"), readonly=True)
        assert bd.path == Path("/home/user/docs")
        assert bd.readonly is True

    def test_create_readwrite(self):
        """Create a read-write bound directory."""
        bd = BoundDirectory(path=Path("/tmp/workspace"), readonly=False)
        assert bd.path == Path("/tmp/workspace")
        assert bd.readonly is False

    def test_default_readonly(self):
        """Default is readonly=True."""
        bd = BoundDirectory(path=Path("/some/path"))
        assert bd.readonly is True


class TestBoundDirectoryStr:
    """Test BoundDirectory __str__ method."""

    def test_str_readonly(self):
        """String representation for readonly."""
        bd = BoundDirectory(path=Path("/home/user/docs"), readonly=True)
        assert str(bd) == "/home/user/docs (ro)"

    def test_str_readwrite(self):
        """String representation for read-write."""
        bd = BoundDirectory(path=Path("/tmp/workspace"), readonly=False)
        assert str(bd) == "/tmp/workspace (rw)"


class TestBoundDirectoryToArgs:
    """Test BoundDirectory to_args() method."""

    def test_to_args_readonly(self, bound_dir_readonly):
        """Readonly produces --ro-bind."""
        args = bound_dir_readonly.to_args()
        assert args[0] == "--ro-bind"
        assert args[1] == str(bound_dir_readonly.path)
        assert args[2] == str(bound_dir_readonly.path)

    def test_to_args_readwrite(self, bound_dir_readwrite):
        """Read-write produces --bind."""
        args = bound_dir_readwrite.to_args()
        assert args[0] == "--bind"
        assert args[1] == str(bound_dir_readwrite.path)
        assert args[2] == str(bound_dir_readwrite.path)

    def test_to_args_format(self):
        """Args format is [flag, src, dest] with same path."""
        bd = BoundDirectory(path=Path("/data"), readonly=True)
        args = bd.to_args()
        assert len(args) == 3
        # Source and dest are the same
        assert args[1] == args[2]

    def test_to_args_path_conversion(self):
        """Path is converted to string."""
        bd = BoundDirectory(path=Path("/home/user/data"), readonly=True)
        args = bd.to_args()
        assert isinstance(args[1], str)
        assert args[1] == "/home/user/data"

    def test_to_args_various_paths(self):
        """Test various path types."""
        test_cases = [
            Path("/"),
            Path("/home"),
            Path("/home/user/documents/project"),
            Path("/tmp"),
        ]
        for path in test_cases:
            bd = BoundDirectory(path=path, readonly=True)
            args = bd.to_args()
            assert args[1] == str(path)
            assert args[2] == str(path)
