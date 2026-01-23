"""Tests for system detection utilities."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from detection import (
    RuntimeDirError,
    detect_dbus_session,
    detect_display_server,
    find_dns_paths,
    find_ssl_cert_paths,
    get_runtime_dir,
    is_path_covered,
    resolve_command_executable,
)
from model import BoundDirectory


class TestGetRuntimeDir:
    """Test get_runtime_dir() function."""

    def test_valid_runtime_dir(self, tmp_path):
        """Valid XDG_RUNTIME_DIR is returned."""
        # Create a temp dir with correct permissions
        runtime_dir = tmp_path / "runtime"
        runtime_dir.mkdir(mode=0o700)

        with patch.dict("os.environ", {"XDG_RUNTIME_DIR": str(runtime_dir)}, clear=True):
            with patch("os.getuid", return_value=runtime_dir.stat().st_uid):
                result = get_runtime_dir()
                assert result == runtime_dir

    def test_nonexistent_runtime_dir_raises(self, tmp_path):
        """Non-existent XDG_RUNTIME_DIR raises RuntimeDirError."""
        nonexistent = tmp_path / "does_not_exist"

        with patch.dict("os.environ", {"XDG_RUNTIME_DIR": str(nonexistent)}, clear=True):
            with pytest.raises(RuntimeDirError) as exc_info:
                get_runtime_dir()
            assert "does not exist" in str(exc_info.value)

    def test_wrong_owner_raises(self, tmp_path):
        """XDG_RUNTIME_DIR owned by wrong user raises RuntimeDirError."""
        runtime_dir = tmp_path / "runtime"
        runtime_dir.mkdir(mode=0o700)
        actual_uid = runtime_dir.stat().st_uid

        with patch.dict("os.environ", {"XDG_RUNTIME_DIR": str(runtime_dir)}, clear=True):
            # Pretend we're a different user
            with patch("os.getuid", return_value=actual_uid + 1):
                with pytest.raises(RuntimeDirError) as exc_info:
                    get_runtime_dir()
                assert "not owned by current user" in str(exc_info.value)

    def test_wrong_permissions_raises(self, tmp_path):
        """XDG_RUNTIME_DIR with wrong permissions raises RuntimeDirError."""
        runtime_dir = tmp_path / "runtime"
        runtime_dir.mkdir(mode=0o755)  # Wrong: group/other readable

        with patch.dict("os.environ", {"XDG_RUNTIME_DIR": str(runtime_dir)}, clear=True):
            with patch("os.getuid", return_value=runtime_dir.stat().st_uid):
                with pytest.raises(RuntimeDirError) as exc_info:
                    get_runtime_dir()
                assert "insecure permissions" in str(exc_info.value)

    def test_no_env_uses_default(self):
        """No XDG_RUNTIME_DIR uses default /run/user/{uid}."""
        with patch.dict("os.environ", {}, clear=True):
            with patch("os.getuid", return_value=1000):
                result = get_runtime_dir()
                assert result == Path("/run/user/1000")


class TestDetectDisplayServer:
    """Test detect_display_server() function."""

    @patch("detection.get_runtime_dir")
    def test_no_display_server(self, mock_runtime_dir, mock_env):
        """No display server when env vars unset."""
        mock_runtime_dir.return_value = Path("/run/user/1000")
        result = detect_display_server()
        assert result.type is None
        assert result.paths == []
        assert result.env_vars == []

    @patch("detection.get_runtime_dir")
    @patch("detection.Path.exists")
    @patch.dict(
        "os.environ",
        {"WAYLAND_DISPLAY": "wayland-0"},
        clear=True,
    )
    def test_wayland_detected(self, mock_exists, mock_runtime_dir):
        """Wayland detected when socket exists."""
        mock_runtime_dir.return_value = Path("/run/user/1000")
        mock_exists.return_value = True
        result = detect_display_server()
        assert result.type == "wayland"
        assert "/run/user/1000/wayland-0" in result.paths
        assert "WAYLAND_DISPLAY" in result.env_vars
        assert "XDG_RUNTIME_DIR" in result.env_vars

    @patch("detection.get_runtime_dir")
    @patch("detection.Path.exists")
    @patch.dict(
        "os.environ",
        {"WAYLAND_DISPLAY": "wayland-0"},
        clear=True,
    )
    def test_wayland_socket_missing(self, mock_exists, mock_runtime_dir):
        """Wayland not detected if socket doesn't exist."""
        mock_runtime_dir.return_value = Path("/run/user/1000")
        mock_exists.return_value = False
        result = detect_display_server()
        assert result.type is None

    @patch("detection.get_runtime_dir")
    @patch("detection.Path.exists")
    @patch.dict("os.environ", {"DISPLAY": ":0"}, clear=True)
    def test_x11_detected(self, mock_exists, mock_runtime_dir):
        """X11 detected when socket exists."""
        mock_runtime_dir.return_value = Path("/run/user/1000")
        mock_exists.return_value = True
        result = detect_display_server()
        assert result.type == "x11"
        assert "DISPLAY" in result.env_vars
        assert "/tmp/.X11-unix" in result.paths

    @patch("detection.get_runtime_dir")
    @patch("detection.Path.exists")
    @patch.dict(
        "os.environ",
        {
            "WAYLAND_DISPLAY": "wayland-0",
            "DISPLAY": ":0",
        },
        clear=True,
    )
    def test_both_detected(self, mock_exists, mock_runtime_dir):
        """Both X11 and Wayland detected."""
        mock_runtime_dir.return_value = Path("/run/user/1000")
        mock_exists.return_value = True
        result = detect_display_server()
        assert result.type == "both"
        assert "DISPLAY" in result.env_vars
        assert "WAYLAND_DISPLAY" in result.env_vars

    @patch("detection.get_runtime_dir")
    @patch("detection.Path.exists")
    @patch.dict(
        "os.environ",
        {"DISPLAY": ":0", "XAUTHORITY": "/home/user/.Xauthority"},
        clear=True,
    )
    def test_xauthority_included(self, mock_exists, mock_runtime_dir):
        """XAUTHORITY path included when it exists."""
        mock_runtime_dir.return_value = Path("/run/user/1000")
        mock_exists.return_value = True
        result = detect_display_server()
        assert "/home/user/.Xauthority" in result.paths
        assert "XAUTHORITY" in result.env_vars


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

    @patch("detection.get_runtime_dir")
    def test_no_dbus_without_env(self, mock_runtime_dir, mock_env):
        """No D-Bus paths without relevant env vars."""
        mock_runtime_dir.return_value = Path("/run/user/1000")
        with patch("detection.Path.exists", return_value=False):
            paths = detect_dbus_session()
            assert paths == []

    @patch("detection.get_runtime_dir")
    @patch("detection.Path.exists")
    def test_standard_bus_path(self, mock_exists, mock_runtime_dir):
        """Finds standard bus path in XDG_RUNTIME_DIR."""
        mock_runtime_dir.return_value = Path("/run/user/1000")
        mock_exists.return_value = True
        paths = detect_dbus_session()
        assert "/run/user/1000/bus" in paths

    @patch("detection.get_runtime_dir")
    @patch("detection.Path.exists")
    @patch.dict(
        "os.environ",
        {"DBUS_SESSION_BUS_ADDRESS": "unix:path=/custom/socket"},
        clear=True,
    )
    def test_custom_dbus_address(self, mock_exists, mock_runtime_dir):
        """Parses DBUS_SESSION_BUS_ADDRESS for custom socket."""
        mock_runtime_dir.return_value = Path("/run/user/1000")
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
