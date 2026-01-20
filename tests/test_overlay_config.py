"""Tests for OverlayConfig model."""

from pathlib import Path

import pytest

from model import OverlayConfig


class TestOverlayConfig:
    """Test OverlayConfig dataclass."""

    def test_create_tmpfs(self):
        """Create a tmpfs overlay."""
        ov = OverlayConfig(source="/src", dest="/dest", mode="tmpfs")
        assert ov.source == "/src"
        assert ov.dest == "/dest"
        assert ov.mode == "tmpfs"
        assert ov.write_dir == ""

    def test_create_persistent(self):
        """Create a persistent overlay."""
        ov = OverlayConfig(
            source="/src",
            dest="/dest",
            mode="persistent",
            write_dir="/writes",
        )
        assert ov.source == "/src"
        assert ov.dest == "/dest"
        assert ov.mode == "persistent"
        assert ov.write_dir == "/writes"

    def test_default_mode(self):
        """Default mode is tmpfs."""
        ov = OverlayConfig(source="/src", dest="/dest")
        assert ov.mode == "tmpfs"


class TestOverlayConfigGetWorkDir:
    """Test OverlayConfig get_work_dir() method."""

    def test_work_dir_from_write_dir(self):
        """Work dir is derived from write dir's parent."""
        ov = OverlayConfig(
            source="/src",
            dest="/dest",
            mode="persistent",
            write_dir="/var/writes/overlay",
        )
        work_dir = ov.get_work_dir()
        assert work_dir == "/var/writes/.overlay-work"

    def test_work_dir_empty_when_no_write_dir(self):
        """Work dir is empty when write_dir is not set."""
        ov = OverlayConfig(source="/src", dest="/dest", mode="tmpfs")
        assert ov.get_work_dir() == ""

    def test_work_dir_various_paths(self):
        """Test work dir calculation for various write_dir values."""
        test_cases = [
            ("/home/user/writes", "/home/user/.overlay-work"),
            ("/tmp/overlay-data", "/tmp/.overlay-work"),
            ("/var/lib/sandbox/writes", "/var/lib/sandbox/.overlay-work"),
        ]
        for write_dir, expected_work in test_cases:
            ov = OverlayConfig(
                source="/src",
                dest="/dest",
                mode="persistent",
                write_dir=write_dir,
            )
            assert ov.get_work_dir() == expected_work


class TestOverlayConfigToArgs:
    """Test OverlayConfig to_args() method."""

    def test_to_args_tmpfs(self, overlay_tmpfs):
        """Tmpfs mode produces simple --tmpfs (empty writable dir)."""
        args = overlay_tmpfs.to_args()
        assert args == ["--tmpfs", "/data"]

    def test_to_args_overlay(self, overlay_overlay):
        """Overlay mode produces --overlay-src and --tmp-overlay."""
        args = overlay_overlay.to_args()
        assert "--overlay-src" in args
        assert "--tmp-overlay" in args
        # Check structure
        src_idx = args.index("--overlay-src")
        assert args[src_idx + 1] == overlay_overlay.source
        tmp_idx = args.index("--tmp-overlay")
        assert args[tmp_idx + 1] == overlay_overlay.dest

    def test_to_args_persistent(self, overlay_persistent):
        """Persistent mode produces --overlay-src and --overlay."""
        args = overlay_persistent.to_args()
        assert "--overlay-src" in args
        assert "--overlay" in args
        # Check structure
        src_idx = args.index("--overlay-src")
        assert args[src_idx + 1] == overlay_persistent.source
        overlay_idx = args.index("--overlay")
        # --overlay takes: write_dir, work_dir, dest
        assert args[overlay_idx + 1] == overlay_persistent.write_dir
        assert args[overlay_idx + 2] == overlay_persistent.get_work_dir()
        assert args[overlay_idx + 3] == overlay_persistent.dest

    def test_to_args_overlay_without_source(self):
        """Overlay mode without source returns empty args (invalid config)."""
        ov = OverlayConfig(source="", dest="/dest", mode="overlay")
        args = ov.to_args()
        assert args == []

    def test_to_args_persistent_without_source(self):
        """Persistent mode without source binds write_dir directly."""
        ov = OverlayConfig(source="", dest="/dest", mode="persistent", write_dir="/write")
        args = ov.to_args()
        # Without source, bind write_dir directly (no overlay layers needed)
        assert args == ["--bind", "/write", "/dest"]

    def test_to_args_empty_dest(self):
        """Empty dest returns empty args."""
        ov = OverlayConfig(source="/src", dest="", mode="overlay")
        assert ov.to_args() == []

    def test_to_args_persistent_without_write_dir(self):
        """Persistent mode without write_dir returns no args (invalid config)."""
        ov = OverlayConfig(
            source="/src",
            dest="/dest",
            mode="persistent",
            write_dir="",
        )
        args = ov.to_args()
        # Persistent requires write_dir, so no args generated
        assert args == []

    def test_to_args_order(self):
        """Args are in correct order: --overlay-src first for overlay mode."""
        ov = OverlayConfig(source="/src", dest="/dest", mode="overlay")
        args = ov.to_args()
        assert args[0] == "--overlay-src"
        assert args[1] == "/src"
        assert args[2] == "--tmp-overlay"
        assert args[3] == "/dest"
