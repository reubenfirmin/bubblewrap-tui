"""Tests for virtual_files module."""

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from model import SandboxConfig
from virtual_files import VirtualFile, VirtualFileManager, create_virtual_files


class TestVirtualFile:
    """Tests for VirtualFile dataclass."""

    def test_creation(self):
        """VirtualFile can be created with all fields."""
        vf = VirtualFile(
            source_path="/tmp/passwd",
            dest_path="/etc/passwd",
            description="Synthetic user identity",
        )
        assert vf.source_path == "/tmp/passwd"
        assert vf.dest_path == "/etc/passwd"
        assert vf.description == "Synthetic user identity"


class TestVirtualFileManager:
    """Tests for VirtualFileManager class."""

    def test_creates_temp_directory(self):
        """Manager creates a temp directory on init."""
        manager = VirtualFileManager()
        assert manager.tmp_dir
        assert os.path.isdir(manager.tmp_dir)
        assert "bui-vfiles-" in manager.tmp_dir

    def test_add_file_creates_file(self):
        """add_file creates a temp file with correct content."""
        manager = VirtualFileManager()
        content = "root:x:0:0:root:/root:/bin/bash"

        path = manager.add_file(content, "/etc/passwd", "Test passwd")

        assert os.path.exists(path)
        assert Path(path).read_text() == content
        # File should be read-only
        assert (os.stat(path).st_mode & 0o777) == 0o444

    def test_add_file_tracks_in_files_list(self):
        """add_file adds VirtualFile to the files list."""
        manager = VirtualFileManager()

        manager.add_file("content", "/etc/passwd", "Passwd file")

        assert len(manager.files) == 1
        assert manager.files[0].dest_path == "/etc/passwd"
        assert manager.files[0].description == "Passwd file"

    def test_add_multiple_files(self):
        """Can add multiple virtual files."""
        manager = VirtualFileManager()

        manager.add_file("passwd content", "/etc/passwd", "Passwd")
        manager.add_file("group content", "/etc/group", "Group")

        assert len(manager.files) == 2

    def test_get_file_map(self):
        """get_file_map returns dest_path -> source_path mapping."""
        manager = VirtualFileManager()

        passwd_path = manager.add_file("passwd", "/etc/passwd", "Passwd")
        group_path = manager.add_file("group", "/etc/group", "Group")

        file_map = manager.get_file_map()

        assert file_map["/etc/passwd"] == passwd_path
        assert file_map["/etc/group"] == group_path

    def test_get_file_map_empty(self):
        """get_file_map returns empty dict when no files added."""
        manager = VirtualFileManager()
        assert manager.get_file_map() == {}

    def test_get_summary(self):
        """get_summary returns human-readable list."""
        manager = VirtualFileManager()

        manager.add_file("passwd", "/etc/passwd", "Synthetic user identity")
        manager.add_file("group", "/etc/group", "Synthetic group")

        summary = manager.get_summary()

        assert len(summary) == 2
        assert "/etc/passwd: Synthetic user identity" in summary
        assert "/etc/group: Synthetic group" in summary

    def test_get_bwrap_args(self):
        """get_bwrap_args returns correct --ro-bind arguments."""
        manager = VirtualFileManager()

        passwd_path = manager.add_file("passwd", "/etc/passwd", "Passwd")
        group_path = manager.add_file("group", "/etc/group", "Group")

        args = manager.get_bwrap_args()

        assert "--ro-bind" in args
        assert passwd_path in args
        assert "/etc/passwd" in args
        assert group_path in args
        assert "/etc/group" in args

    def test_get_bwrap_args_empty(self):
        """get_bwrap_args returns empty list when no files added."""
        manager = VirtualFileManager()
        assert manager.get_bwrap_args() == []

    def test_filename_derived_from_dest_path(self):
        """Temp filename is derived from dest_path."""
        manager = VirtualFileManager()

        path = manager.add_file("content", "/etc/passwd", "Desc")

        assert Path(path).name == "passwd"


class TestCreateVirtualFiles:
    """Tests for create_virtual_files function."""

    def test_creates_manager(self):
        """create_virtual_files returns a VirtualFileManager."""
        config = SandboxConfig(command=["bash"])
        manager = create_virtual_files(config)
        assert isinstance(manager, VirtualFileManager)

    def test_no_files_without_synthetic_passwd(self):
        """No virtual files created when synthetic_passwd is disabled."""
        config = SandboxConfig(command=["bash"])
        config.user.synthetic_passwd = False

        manager = create_virtual_files(config)

        assert len(manager.files) == 0

    def test_creates_passwd_group_with_synthetic_user(self):
        """Creates passwd and group files when synthetic_passwd is enabled."""
        config = SandboxConfig(command=["bash"])
        config.user.unshare_user = True
        config.user.synthetic_passwd = True
        config.user.username = "testuser"
        config.user.uid = 1000
        config.user.gid = 1000

        manager = create_virtual_files(config)

        file_map = manager.get_file_map()
        assert "/etc/passwd" in file_map
        assert "/etc/group" in file_map

        # Check passwd content
        passwd_content = Path(file_map["/etc/passwd"]).read_text()
        assert "testuser" in passwd_content
        assert "1000" in passwd_content

    def test_passwd_description(self):
        """Virtual files have appropriate descriptions."""
        config = SandboxConfig(command=["bash"])
        config.user.unshare_user = True
        config.user.synthetic_passwd = True
        config.user.username = "testuser"
        config.user.uid = 1000
        config.user.gid = 1000

        manager = create_virtual_files(config)

        summary = manager.get_summary()
        assert any("Synthetic user identity" in s for s in summary)
        assert any("Synthetic group" in s for s in summary)

    def test_raises_error_when_uid_is_none(self):
        """Raises error when synthetic_passwd enabled but uid is None."""
        config = SandboxConfig(command=["bash"])
        config.user.unshare_user = True
        config.user.synthetic_passwd = True
        config.user.username = "testuser"
        config.user.uid = None  # Missing uid
        config.user.gid = 1000

        with pytest.raises(ValueError) as exc_info:
            create_virtual_files(config)
        assert "uid" in str(exc_info.value)
        assert "testuser" in str(exc_info.value)

    def test_raises_error_when_gid_is_none(self):
        """Raises error when synthetic_passwd enabled but gid is None."""
        config = SandboxConfig(command=["bash"])
        config.user.unshare_user = True
        config.user.synthetic_passwd = True
        config.user.username = "testuser"
        config.user.uid = 1000
        config.user.gid = None  # Missing gid

        with pytest.raises(ValueError) as exc_info:
            create_virtual_files(config)
        assert "gid" in str(exc_info.value)
        assert "testuser" in str(exc_info.value)


class TestVirtualFileManagerCleanup:
    """Tests for temp directory cleanup on failure."""

    def test_add_file_cleans_up_on_write_failure(self):
        """Temp directory is cleaned up if file write fails."""
        manager = VirtualFileManager()
        tmp_dir = manager.tmp_dir

        # Verify temp dir exists
        assert os.path.isdir(tmp_dir)

        # Mock write_file_atomic to raise OSError
        with patch("virtual_files.write_file_atomic", side_effect=OSError("Disk full")):
            with pytest.raises(OSError):
                manager.add_file("content", "/etc/passwd", "Test")

        # Temp directory should be cleaned up
        assert not os.path.exists(tmp_dir)

    def test_add_file_reraises_exception(self):
        """OSError is re-raised after cleanup."""
        manager = VirtualFileManager()

        with patch("virtual_files.write_file_atomic", side_effect=OSError("Permission denied")):
            with pytest.raises(OSError, match="Permission denied"):
                manager.add_file("content", "/etc/passwd", "Test")
