"""Tests for system detection utilities."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from detection import (
    detect_dbus_session,
    detect_display_server,
    find_dns_paths,
    find_ssl_cert_paths,
    is_path_covered,
    resolve_command_executable,
)
from model import BoundDirectory


class TestDetectDisplayServer:
    """Test detect_display_server() function."""

    def test_no_display_server(self, mock_env):
        """No display server when env vars unset."""
        result = detect_display_server()
        assert result["type"] is None
        assert result["paths"] == []
        assert result["env_vars"] == []

    @patch("detection.Path.exists")
    @patch.dict(
        "os.environ",
        {"WAYLAND_DISPLAY": "wayland-0", "XDG_RUNTIME_DIR": "/run/user/1000"},
        clear=True,
    )
    def test_wayland_detected(self, mock_exists):
        """Wayland detected when socket exists."""
        mock_exists.return_value = True
        result = detect_display_server()
        assert result["type"] == "wayland"
        assert "/run/user/1000/wayland-0" in result["paths"]
        assert "WAYLAND_DISPLAY" in result["env_vars"]
        assert "XDG_RUNTIME_DIR" in result["env_vars"]

    @patch("detection.Path.exists")
    @patch.dict(
        "os.environ",
        {"WAYLAND_DISPLAY": "wayland-0", "XDG_RUNTIME_DIR": "/run/user/1000"},
        clear=True,
    )
    def test_wayland_socket_missing(self, mock_exists):
        """Wayland not detected if socket doesn't exist."""
        mock_exists.return_value = False
        result = detect_display_server()
        assert result["type"] is None

    @patch("detection.Path.exists")
    @patch.dict("os.environ", {"DISPLAY": ":0"}, clear=True)
    def test_x11_detected(self, mock_exists):
        """X11 detected when socket exists."""
        mock_exists.return_value = True
        result = detect_display_server()
        assert result["type"] == "x11"
        assert "DISPLAY" in result["env_vars"]
        assert "/tmp/.X11-unix" in result["paths"]

    @patch("detection.Path.exists")
    @patch.dict(
        "os.environ",
        {
            "WAYLAND_DISPLAY": "wayland-0",
            "DISPLAY": ":0",
            "XDG_RUNTIME_DIR": "/run/user/1000",
        },
        clear=True,
    )
    def test_both_detected(self, mock_exists):
        """Both X11 and Wayland detected."""
        mock_exists.return_value = True
        result = detect_display_server()
        assert result["type"] == "both"
        assert "DISPLAY" in result["env_vars"]
        assert "WAYLAND_DISPLAY" in result["env_vars"]

    @patch("detection.Path.exists")
    @patch.dict(
        "os.environ",
        {"DISPLAY": ":0", "XAUTHORITY": "/home/user/.Xauthority"},
        clear=True,
    )
    def test_xauthority_included(self, mock_exists):
        """XAUTHORITY path included when it exists."""
        mock_exists.return_value = True
        result = detect_display_server()
        assert "/home/user/.Xauthority" in result["paths"]
        assert "XAUTHORITY" in result["env_vars"]


class TestFindSslCertPaths:
    """Test find_ssl_cert_paths() function."""

    @patch("detection.Path.exists")
    @patch("detection.Path.resolve")
    @patch("detection.Path.is_symlink")
    def test_finds_existing_paths(self, mock_symlink, mock_resolve, mock_exists):
        """Returns only existing paths."""
        mock_exists.return_value = True
        mock_resolve.return_value = Path("/etc/ssl/certs")
        mock_symlink.return_value = False

        paths = find_ssl_cert_paths()
        assert len(paths) > 0

    def test_returns_list(self):
        """Always returns a list."""
        paths = find_ssl_cert_paths()
        assert isinstance(paths, list)


class TestFindDnsPaths:
    """Test find_dns_paths() function."""

    @patch("detection.Path.exists")
    @patch("detection.Path.resolve")
    @patch("detection.Path.is_symlink")
    def test_includes_resolv_conf(self, mock_symlink, mock_resolve, mock_exists):
        """Includes /etc/resolv.conf when it exists."""
        mock_exists.return_value = True
        mock_resolve.return_value = Path("/etc/resolv.conf")
        mock_symlink.return_value = False

        paths = find_dns_paths()
        assert any("resolv.conf" in p for p in paths)

    def test_returns_list(self):
        """Always returns a list."""
        paths = find_dns_paths()
        assert isinstance(paths, list)


class TestDetectDbusSession:
    """Test detect_dbus_session() function."""

    def test_no_dbus_without_env(self, mock_env):
        """No D-Bus paths without relevant env vars."""
        with patch("detection.Path.exists", return_value=False):
            paths = detect_dbus_session()
            assert paths == []

    @patch("detection.Path.exists")
    @patch.dict("os.environ", {"XDG_RUNTIME_DIR": "/run/user/1000"}, clear=True)
    def test_standard_bus_path(self, mock_exists):
        """Finds standard bus path in XDG_RUNTIME_DIR."""
        mock_exists.return_value = True
        paths = detect_dbus_session()
        assert "/run/user/1000/bus" in paths

    @patch("detection.Path.exists")
    @patch.dict(
        "os.environ",
        {"DBUS_SESSION_BUS_ADDRESS": "unix:path=/custom/socket"},
        clear=True,
    )
    def test_custom_dbus_address(self, mock_exists):
        """Parses DBUS_SESSION_BUS_ADDRESS for custom socket."""
        mock_exists.return_value = True
        paths = detect_dbus_session()
        assert "/custom/socket" in paths


class TestResolveCommandExecutable:
    """Test resolve_command_executable() function."""

    def test_empty_command(self):
        """Empty command returns None."""
        assert resolve_command_executable([]) is None

    @patch("os.path.isabs")
    @patch("os.path.isfile")
    @patch("os.access")
    def test_absolute_path_exists(self, mock_access, mock_isfile, mock_isabs):
        """Absolute path that exists and is executable."""
        mock_isabs.return_value = True
        mock_isfile.return_value = True
        mock_access.return_value = True

        result = resolve_command_executable(["/usr/bin/python"])
        assert result is not None

    @patch("os.path.isabs")
    @patch("os.path.isfile")
    def test_absolute_path_not_exists(self, mock_isfile, mock_isabs):
        """Absolute path that doesn't exist returns None."""
        mock_isabs.return_value = True
        mock_isfile.return_value = False

        result = resolve_command_executable(["/nonexistent/binary"])
        assert result is None

    @patch("shutil.which")
    def test_path_lookup(self, mock_which):
        """Non-absolute path is looked up via PATH."""
        mock_which.return_value = "/usr/bin/python"
        result = resolve_command_executable(["python"])
        mock_which.assert_called_with("python")
        assert result == Path("/usr/bin/python").resolve()

    @patch("shutil.which")
    def test_path_lookup_not_found(self, mock_which):
        """Command not in PATH returns None."""
        mock_which.return_value = None
        result = resolve_command_executable(["nonexistent"])
        assert result is None


class TestIsPathCovered:
    """Test is_path_covered() function."""

    def test_path_covered_by_bound_dir(self):
        """Path under a bound directory is covered."""
        bound_dirs = [BoundDirectory(path=Path("/home/user"), readonly=True)]
        result = is_path_covered(Path("/home/user/documents/file.txt"), bound_dirs)
        assert result is True

    def test_path_not_covered_by_bound_dir(self):
        """Path not under any bound directory is not covered."""
        bound_dirs = [BoundDirectory(path=Path("/home/user"), readonly=True)]
        result = is_path_covered(Path("/opt/other/file.txt"), bound_dirs)
        assert result is False

    def test_path_covered_by_system_bind(self):
        """Path under system bind (now in bound_dirs) is covered."""
        # System paths are now added to bound_dirs via quick shortcuts
        bound_dirs = [BoundDirectory(path=Path("/usr"), readonly=True)]
        result = is_path_covered(Path("/usr/bin/python"), bound_dirs)
        assert result is True

    def test_path_not_covered_by_inactive_system_bind(self):
        """Path not in bound_dirs is not covered."""
        # When system bind is not active, it's not in bound_dirs
        bound_dirs = []
        result = is_path_covered(Path("/usr/bin/python"), bound_dirs)
        assert result is False

    def test_exact_path_match(self):
        """Exact path match is covered."""
        bound_dirs = [BoundDirectory(path=Path("/home/user"), readonly=True)]
        result = is_path_covered(Path("/home/user"), bound_dirs)
        assert result is True

    def test_similar_but_not_nested_path(self):
        """Path with similar prefix but not nested is not covered."""
        bound_dirs = [BoundDirectory(path=Path("/home/user"), readonly=True)]
        # /home/user2 is not under /home/user
        result = is_path_covered(Path("/home/user2/file.txt"), bound_dirs)
        assert result is False
