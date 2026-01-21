"""Tests for bwrap command serialization.

This is the most critical test module - it ensures BubblewrapSerializer
correctly translates SandboxConfig into bwrap command-line arguments.
"""

from pathlib import Path
from unittest.mock import patch

import pytest

from bwrap import BubblewrapSerializer
from model import (
    BoundDirectory,
    OverlayConfig,
    SandboxConfig,
)


def make_config(
    command=None,
    filesystem=None,
    network=None,
    user=None,
    namespace=None,
    hostname=None,
    process=None,
    environment=None,
    desktop=None,
    bound_dirs=None,
    overlays=None,
    drop_caps=None,
):
    """Helper to create SandboxConfig with the new group-based architecture."""
    config = SandboxConfig(
        command=command or ["bash"],
        bound_dirs=bound_dirs or [],
        overlays=overlays or [],
        drop_caps=drop_caps or set(),
    )

    # Apply filesystem settings
    if filesystem:
        for key, value in filesystem.items():
            setattr(config.filesystem, key, value)

    # Apply network settings
    if network:
        for key, value in network.items():
            setattr(config.network, key, value)

    # Apply user settings (unshare_user, uid, gid, username)
    if user:
        for key, value in user.items():
            setattr(config.user, key, value)

    # Apply namespace settings (pid, ipc, cgroup)
    if namespace:
        for key, value in namespace.items():
            setattr(config.namespace, key, value)

    # Apply hostname settings (uts namespace + custom hostname)
    if hostname:
        for key, value in hostname.items():
            setattr(config.hostname, key, value)

    # Apply process settings
    if process:
        for key, value in process.items():
            setattr(config.process, key, value)

    # Apply environment settings
    if environment:
        for key, value in environment.items():
            setattr(config.environment, key, value)

    # Apply desktop settings
    if desktop:
        for key, value in desktop.items():
            setattr(config.desktop, key, value)

    return config


class TestBasicSandbox:
    """Test basic sandbox configurations."""

    def test_minimal_config_has_bwrap_and_command(self, minimal_config):
        """Minimal config produces 'bwrap -- <command>'."""
        args = BubblewrapSerializer(minimal_config).serialize()
        assert args[0] == "bwrap"
        assert "--" in args
        sep_idx = args.index("--")
        assert args[sep_idx + 1 :] == ["bash"]

    def test_command_with_arguments(self):
        """Command arguments are preserved."""
        config = SandboxConfig(command=["python", "script.py", "--verbose", "-n", "5"])
        args = BubblewrapSerializer(config).serialize()
        sep_idx = args.index("--")
        assert args[sep_idx + 1 :] == ["python", "script.py", "--verbose", "-n", "5"]


class TestFilesystemBinds:
    """Test filesystem bind arguments."""

    def test_dev_mode_minimal(self):
        """dev_mode='minimal' produces --dev /dev."""
        config = make_config(filesystem={"dev_mode": "minimal"})
        args = BubblewrapSerializer(config).serialize()
        assert "--dev" in args
        dev_idx = args.index("--dev")
        assert args[dev_idx + 1] == "/dev"

    def test_dev_mode_full(self):
        """dev_mode='full' produces --bind /dev /dev."""
        config = make_config(filesystem={"dev_mode": "full"})
        args = BubblewrapSerializer(config).serialize()
        assert "--bind" in args
        bind_indices = [i for i, x in enumerate(args) if x == "--bind"]
        found_dev_bind = False
        for idx in bind_indices:
            if args[idx + 1] == "/dev" and args[idx + 2] == "/dev":
                found_dev_bind = True
                break
        assert found_dev_bind, "Expected --bind /dev /dev for full dev mode"

    def test_dev_mode_none(self):
        """dev_mode='none' produces no /dev args."""
        config = make_config(filesystem={"dev_mode": "none"})
        args = BubblewrapSerializer(config).serialize()
        # Should not have --dev /dev or --bind /dev /dev
        for i, arg in enumerate(args):
            if arg in ("--dev", "--bind") and i + 1 < len(args):
                assert args[i + 1] != "/dev", f"Unexpected /dev bind with {arg}"

    def test_mount_proc(self):
        """mount_proc=True produces --proc /proc."""
        config = make_config(filesystem={"mount_proc": True})
        args = BubblewrapSerializer(config).serialize()
        assert "--proc" in args
        proc_idx = args.index("--proc")
        assert args[proc_idx + 1] == "/proc"

    def test_mount_tmp_without_size(self):
        """mount_tmp=True without size produces --tmpfs /tmp."""
        config = make_config(filesystem={"mount_tmp": True, "tmpfs_size": ""})
        args = BubblewrapSerializer(config).serialize()
        assert "--tmpfs" in args
        tmpfs_idx = args.index("--tmpfs")
        assert args[tmpfs_idx + 1] == "/tmp"

    def test_mount_tmp_with_size(self):
        """mount_tmp=True with size produces --size X --tmpfs /tmp."""
        config = make_config(filesystem={"mount_tmp": True, "tmpfs_size": "100M"})
        args = BubblewrapSerializer(config).serialize()
        assert "--size" in args
        size_idx = args.index("--size")
        assert args[size_idx + 1] == "100M"
        assert args[size_idx + 2] == "--tmpfs"
        assert args[size_idx + 3] == "/tmp"

    @patch("pathlib.Path.exists", return_value=True)
    def test_system_binds_when_paths_exist(self, mock_exists):
        """System binds are added via bound_dirs (Quick Shortcuts flow)."""
        from model import BoundDirectory
        # Quick shortcuts now work through bound_dirs, not config.filesystem values
        config = make_config()
        config.bound_dirs.append(BoundDirectory(path=Path("/usr"), readonly=True))
        config.bound_dirs.append(BoundDirectory(path=Path("/bin"), readonly=True))
        args = BubblewrapSerializer(config).serialize()
        # Should have --ro-bind /usr /usr and --ro-bind /bin /bin
        ro_bind_indices = [i for i, x in enumerate(args) if x == "--ro-bind"]
        bound_paths = [args[i + 1] for i in ro_bind_indices]
        assert "/usr" in bound_paths
        assert "/bin" in bound_paths


class TestNetworkIsolation:
    """Test network-related arguments."""

    def test_network_isolated_by_default(self, minimal_config):
        """Default config has no --share-net."""
        args = BubblewrapSerializer(minimal_config).serialize()
        assert "--share-net" not in args

    def test_share_net_enabled(self):
        """share_net=True produces --share-net."""
        config = make_config(network={"share_net": True})
        args = BubblewrapSerializer(config).serialize()
        assert "--share-net" in args

    @patch("detection.find_dns_paths")
    def test_bind_resolv_conf(self, mock_dns):
        """bind_resolv_conf binds DNS paths."""
        mock_dns.return_value = ["/etc/resolv.conf", "/run/systemd/resolve"]
        config = make_config(network={"bind_resolv_conf": True})
        args = BubblewrapSerializer(config).serialize()
        # Should bind the DNS paths
        assert "/etc/resolv.conf" in args or "/run/systemd/resolve" in args

    @patch("detection.find_ssl_cert_paths")
    def test_bind_ssl_certs(self, mock_certs):
        """bind_ssl_certs binds SSL cert paths."""
        mock_certs.return_value = ["/etc/ssl/certs"]
        config = make_config(network={"bind_ssl_certs": True})
        args = BubblewrapSerializer(config).serialize()
        assert "/etc/ssl/certs" in args


class TestNamespaceOptions:
    """Test namespace isolation arguments."""

    def test_unshare_user(self):
        """unshare_user produces --unshare-user."""
        config = make_config(user={"unshare_user": True})
        args = BubblewrapSerializer(config).serialize()
        assert "--unshare-user" in args

    def test_unshare_pid(self):
        """unshare_pid produces --unshare-pid."""
        config = make_config(namespace={"unshare_pid": True})
        args = BubblewrapSerializer(config).serialize()
        assert "--unshare-pid" in args

    def test_unshare_ipc(self):
        """unshare_ipc produces --unshare-ipc."""
        config = make_config(namespace={"unshare_ipc": True})
        args = BubblewrapSerializer(config).serialize()
        assert "--unshare-ipc" in args

    def test_unshare_uts(self):
        """unshare_uts produces --unshare-uts."""
        config = make_config(namespace={"unshare_uts": True})
        args = BubblewrapSerializer(config).serialize()
        assert "--unshare-uts" in args

    def test_unshare_cgroup(self):
        """unshare_cgroup produces --unshare-cgroup."""
        config = make_config(namespace={"unshare_cgroup": True})
        args = BubblewrapSerializer(config).serialize()
        assert "--unshare-cgroup" in args

    def test_disable_userns(self):
        """disable_userns produces --disable-userns."""
        config = make_config(namespace={"disable_userns": True})
        args = BubblewrapSerializer(config).serialize()
        assert "--disable-userns" in args


class TestProcessOptions:
    """Test process control arguments."""

    def test_die_with_parent(self):
        """die_with_parent produces --die-with-parent."""
        config = make_config(process={"die_with_parent": True})
        args = BubblewrapSerializer(config).serialize()
        assert "--die-with-parent" in args

    def test_new_session(self):
        """new_session produces --new-session."""
        config = make_config(process={"new_session": True})
        args = BubblewrapSerializer(config).serialize()
        assert "--new-session" in args

    def test_as_pid_1_adds_unshare_pid(self):
        """as_pid_1 implies --unshare-pid if not already set."""
        config = make_config(
            namespace={"unshare_pid": False},
            process={"as_pid_1": True},
        )
        args = BubblewrapSerializer(config).serialize()
        assert "--as-pid-1" in args
        assert "--unshare-pid" in args

    def test_as_pid_1_with_existing_unshare_pid(self):
        """as_pid_1 doesn't duplicate --unshare-pid."""
        config = make_config(
            namespace={"unshare_pid": True},
            process={"as_pid_1": True},
        )
        args = BubblewrapSerializer(config).serialize()
        assert "--as-pid-1" in args
        # Should have exactly one --unshare-pid
        assert args.count("--unshare-pid") == 1

    def test_chdir(self):
        """chdir produces --chdir <path>."""
        config = make_config(process={"chdir": "/home/user"})
        args = BubblewrapSerializer(config).serialize()
        assert "--chdir" in args
        chdir_idx = args.index("--chdir")
        assert args[chdir_idx + 1] == "/home/user"

    def test_uid_gid_with_user_namespace(self):
        """UID/GID mapping when user namespace is enabled."""
        config = make_config(
            user={"unshare_user": True, "uid": 1000, "gid": 1000},
        )
        args = BubblewrapSerializer(config).serialize()
        assert "--uid" in args
        assert "--gid" in args
        uid_idx = args.index("--uid")
        gid_idx = args.index("--gid")
        assert args[uid_idx + 1] == "1000"
        assert args[gid_idx + 1] == "1000"

    def test_no_uid_gid_without_user_namespace(self):
        """UID/GID not added without user namespace."""
        config = make_config(
            user={"unshare_user": False, "uid": 1000, "gid": 1000},
        )
        args = BubblewrapSerializer(config).serialize()
        assert "--uid" not in args
        assert "--gid" not in args


class TestBoundDirectories:
    """Test user-specified bound directories."""

    def test_readonly_bound_dir(self):
        """Readonly bound dir produces --ro-bind."""
        config = make_config(
            bound_dirs=[BoundDirectory(path=Path("/home/user/docs"), readonly=True)],
        )
        args = BubblewrapSerializer(config).serialize()
        assert "--ro-bind" in args
        ro_idx = [i for i, x in enumerate(args) if x == "--ro-bind"]
        found = False
        for idx in ro_idx:
            if args[idx + 1] == "/home/user/docs":
                found = True
                assert args[idx + 2] == "/home/user/docs"
        assert found

    def test_readwrite_bound_dir(self):
        """Read-write bound dir produces --bind."""
        config = make_config(
            bound_dirs=[BoundDirectory(path=Path("/home/user/work"), readonly=False)],
        )
        args = BubblewrapSerializer(config).serialize()
        bind_indices = [i for i, x in enumerate(args) if x == "--bind"]
        found = False
        for idx in bind_indices:
            if args[idx + 1] == "/home/user/work":
                found = True
                assert args[idx + 2] == "/home/user/work"
        assert found


class TestOverlays:
    """Test overlay filesystem arguments."""

    def test_tmpfs_empty(self):
        """Tmpfs mode produces simple --tmpfs (empty writable dir)."""
        config = make_config(
            overlays=[OverlayConfig(source="", dest="/data", mode="tmpfs")],
        )
        args = BubblewrapSerializer(config).serialize()
        # Find --tmpfs /data (not the default /tmp)
        found = False
        for i, arg in enumerate(args):
            if arg == "--tmpfs" and i + 1 < len(args) and args[i + 1] == "/data":
                found = True
                break
        assert found, f"Expected --tmpfs /data in args: {args}"
        # Should not have overlay-src
        assert "--overlay-src" not in args

    def test_overlay_mode(self):
        """Overlay mode produces --overlay-src and --tmp-overlay."""
        config = make_config(
            overlays=[OverlayConfig(source="/src", dest="/dest", mode="overlay")],
        )
        args = BubblewrapSerializer(config).serialize()
        assert "--overlay-src" in args
        src_idx = args.index("--overlay-src")
        assert args[src_idx + 1] == "/src"
        assert "--tmp-overlay" in args
        tmp_idx = args.index("--tmp-overlay")
        assert args[tmp_idx + 1] == "/dest"

    def test_persistent_overlay(self):
        """Persistent overlay produces --overlay-src and --overlay."""
        config = make_config(
            overlays=[
                OverlayConfig(
                    source="/src",
                    dest="/dest",
                    mode="persistent",
                    write_dir="/writes",
                )
            ],
        )
        args = BubblewrapSerializer(config).serialize()
        assert "--overlay-src" in args
        assert "--overlay" in args
        overlay_idx = args.index("--overlay")
        assert args[overlay_idx + 1] == "/writes"


class TestCapabilities:
    """Test capability drop arguments."""

    def test_drop_caps(self):
        """Dropping capabilities produces --cap-drop."""
        config = make_config(drop_caps={"CAP_NET_RAW", "CAP_SYS_ADMIN"})
        args = BubblewrapSerializer(config).serialize()
        cap_drop_indices = [i for i, x in enumerate(args) if x == "--cap-drop"]
        dropped_caps = {args[i + 1] for i in cap_drop_indices}
        assert "CAP_NET_RAW" in dropped_caps
        assert "CAP_SYS_ADMIN" in dropped_caps


class TestEnvironment:
    """Test environment variable arguments."""

    def test_clear_env(self):
        """clear_env produces --clearenv."""
        config = make_config(environment={"clear_env": True})
        args = BubblewrapSerializer(config).serialize()
        assert "--clearenv" in args

    @patch.dict("os.environ", {"PATH": "/usr/bin", "HOME": "/home/user"}, clear=True)
    def test_keep_env_vars_with_clearenv(self):
        """Kept env vars are re-set after --clearenv."""
        config = make_config(
            environment={
                "clear_env": True,
                "keep_env_vars": {"PATH"},
            },
        )
        args = BubblewrapSerializer(config).serialize()
        assert "--clearenv" in args
        assert "--setenv" in args
        setenv_idx = args.index("--setenv")
        assert args[setenv_idx + 1] == "PATH"
        assert args[setenv_idx + 2] == "/usr/bin"

    def test_unset_env_vars(self):
        """Unset env vars produce --unsetenv."""
        config = make_config(
            environment={
                "clear_env": False,
                "unset_env_vars": {"SECRET_VAR"},
            },
        )
        args = BubblewrapSerializer(config).serialize()
        assert "--unsetenv" in args
        unset_idx = args.index("--unsetenv")
        assert args[unset_idx + 1] == "SECRET_VAR"

    def test_custom_env_vars(self):
        """Custom env vars produce --setenv."""
        config = make_config(
            environment={"custom_env_vars": {"MY_VAR": "my_value"}},
        )
        args = BubblewrapSerializer(config).serialize()
        assert "--setenv" in args
        # Find the custom var setenv
        for i, arg in enumerate(args):
            if arg == "--setenv" and i + 1 < len(args) and args[i + 1] == "MY_VAR":
                assert args[i + 2] == "my_value"
                break
        else:
            pytest.fail("Custom env var not found")

    def test_custom_hostname(self):
        """Custom hostname produces --hostname."""
        config = make_config(hostname={"custom_hostname": "sandbox"})
        args = BubblewrapSerializer(config).serialize()
        assert "--hostname" in args
        hostname_idx = args.index("--hostname")
        assert args[hostname_idx + 1] == "sandbox"


class TestDesktopIntegration:
    """Test desktop integration arguments."""

    @patch("detection.detect_dbus_session")
    def test_allow_dbus(self, mock_dbus):
        """allow_dbus binds D-Bus paths."""
        mock_dbus.return_value = ["/run/user/1000/bus"]
        config = make_config(desktop={"allow_dbus": True})
        args = BubblewrapSerializer(config).serialize()
        assert "/run/user/1000/bus" in args

    @patch("detection.detect_display_server")
    def test_allow_display(self, mock_display):
        """allow_display binds display paths."""
        from detection import DisplayServerInfo
        mock_display.return_value = DisplayServerInfo(
            type="x11",
            paths=["/tmp/.X11-unix"],
            env_vars=["DISPLAY"],
        )
        config = make_config(desktop={"allow_display": True})
        args = BubblewrapSerializer(config).serialize()
        assert "/tmp/.X11-unix" in args

    @patch("pathlib.Path.exists", return_value=True)
    @patch("pathlib.Path.home")
    def test_bind_user_config(self, mock_home, mock_exists):
        """bind_user_config binds ~/.config via bound_dirs (Quick Shortcuts flow)."""
        from model import BoundDirectory
        mock_home.return_value = Path("/home/testuser")
        # Quick shortcuts now work through bound_dirs, not config.desktop values
        config = make_config()
        config.bound_dirs.append(BoundDirectory(path=Path("/home/testuser/.config"), readonly=True))
        args = BubblewrapSerializer(config).serialize()
        assert "/home/testuser/.config" in args


class TestFullConfig:
    """Test with full_config fixture for integration."""

    def test_full_config_serializes(self, full_config):
        """Full config produces valid bwrap args."""
        args = BubblewrapSerializer(full_config).serialize()
        assert args[0] == "bwrap"
        assert "--" in args
        # Command is at the end
        sep_idx = args.index("--")
        assert args[sep_idx + 1 :] == ["python", "script.py", "--arg"]

    def test_full_config_has_expected_flags(self, full_config):
        """Full config includes expected flags."""
        args = BubblewrapSerializer(full_config).serialize()
        # From namespace config
        assert "--unshare-user" in args
        assert "--unshare-pid" in args
        assert "--unshare-ipc" in args
        # From process config
        assert "--die-with-parent" in args
        assert "--new-session" in args
        assert "--chdir" in args
        # From environment
        assert "--clearenv" in args
        assert "--hostname" in args
        # From network
        assert "--share-net" in args


class TestVirtualUser:
    """Test virtual user (synthetic passwd/group) features."""

    def test_get_virtual_user_data_with_username(self):
        """Virtual user data is generated when username and uid > 0."""
        config = make_config(
            user={"unshare_user": True, "uid": 1000, "gid": 1000, "username": "testuser"}
        )
        serializer = BubblewrapSerializer(config)
        data = serializer.get_virtual_user_data()
        assert len(data) == 2
        # Check passwd content
        passwd_content, passwd_path = data[0]
        assert passwd_path == "/etc/passwd"
        assert "testuser:x:1000:1000" in passwd_content
        assert "/home/testuser" in passwd_content
        # Check group content
        group_content, group_path = data[1]
        assert group_path == "/etc/group"
        assert "testuser:x:1000" in group_content

    def test_get_virtual_user_data_uid_zero(self):
        """No virtual user data for uid 0 (root)."""
        config = make_config(
            user={"unshare_user": True, "uid": 0, "gid": 0, "username": ""}
        )
        serializer = BubblewrapSerializer(config)
        data = serializer.get_virtual_user_data()
        assert data == []

    def test_get_virtual_user_data_no_username(self):
        """No virtual user data when username is empty."""
        config = make_config(
            user={"unshare_user": True, "uid": 1000, "gid": 1000, "username": ""}
        )
        serializer = BubblewrapSerializer(config)
        data = serializer.get_virtual_user_data()
        assert data == []

    def test_serialize_virtual_user_args_with_fd_map(self):
        """Virtual user args include FD bindings when fd_map provided."""
        config = make_config(
            user={"unshare_user": True, "uid": 1000, "gid": 1000, "username": "testuser"}
        )
        serializer = BubblewrapSerializer(config)
        fd_map = {"/etc/passwd": 4, "/etc/group": 5}
        args = serializer.serialize(fd_map=fd_map)
        # Should have FD bindings
        assert "--ro-bind-data" in args
        assert "4" in args
        assert "5" in args
        assert "/etc/passwd" in args
        assert "/etc/group" in args

    def test_serialize_virtual_user_creates_home_dir(self):
        """Virtual user args create home directory when no home overlay exists."""
        config = make_config(
            user={
                "unshare_user": True,
                "uid": 1000,
                "gid": 1000,
                "username": "testuser",
                "synthetic_passwd": True,
            }
        )
        serializer = BubblewrapSerializer(config)
        fd_map = {"/etc/passwd": 4, "/etc/group": 5}
        args = serializer.serialize(fd_map=fd_map)
        # Should create /home and /home/testuser directories
        home_dir_indices = [i for i, x in enumerate(args) if x == "--dir"]
        home_dirs = [args[i + 1] for i in home_dir_indices if i + 1 < len(args)]
        assert "/home" in home_dirs
        assert "/home/testuser" in home_dirs
        # Should set HOME env var
        assert "--setenv" in args
        for i, arg in enumerate(args):
            if arg == "--setenv" and i + 1 < len(args) and args[i + 1] == "HOME":
                assert args[i + 2] == "/home/testuser"
                break
        else:
            pytest.fail("HOME env var not set")

    def test_serialize_virtual_user_creates_etc(self):
        """When synthetic_passwd enabled and username set with uid > 0, --dir /etc is created."""
        config = make_config(
            user={
                "unshare_user": True,
                "uid": 1000,
                "gid": 1000,
                "username": "testuser",
                "synthetic_passwd": True,
            }
        )
        serializer = BubblewrapSerializer(config)
        fd_map = {"/etc/passwd": 4, "/etc/group": 5}
        args = serializer.serialize(fd_map=fd_map)
        # Should have --dir /etc for synthetic passwd/group
        dir_indices = [i for i, x in enumerate(args) if x == "--dir"]
        dirs_created = [args[i + 1] for i in dir_indices if i + 1 < len(args)]
        assert "/etc" in dirs_created

    def test_serialize_virtual_user_with_home_overlay(self):
        """When home overlay exists, home dirs are not created (overlay handles it)."""
        config = make_config(
            user={
                "unshare_user": True,
                "uid": 1000,
                "gid": 1000,
                "username": "testuser",
                "synthetic_passwd": True,
            },
            overlays=[OverlayConfig(source="", dest="/home/testuser", mode="tmpfs")],
        )
        serializer = BubblewrapSerializer(config)
        fd_map = {"/etc/passwd": 4, "/etc/group": 5}
        args = serializer.serialize(fd_map=fd_map)
        # Should NOT have --dir /home or --dir /home/testuser (overlay handles it)
        dir_indices = [i for i, x in enumerate(args) if x == "--dir"]
        dirs_created = [args[i + 1] for i in dir_indices if i + 1 < len(args)]
        assert "/home" not in dirs_created
        assert "/home/testuser" not in dirs_created
        # Should NOT set HOME (overlay handler does this)
        home_set = False
        for i, arg in enumerate(args):
            if arg == "--setenv" and i + 1 < len(args) and args[i + 1] == "HOME":
                home_set = True
                break
        assert not home_set


class TestOverlayModes:
    """Test the three overlay modes in detail."""

    def test_tmpfs_mode_no_source(self):
        """Tmpfs mode creates simple --tmpfs without source."""
        config = make_config(
            overlays=[OverlayConfig(source="", dest="/data", mode="tmpfs")]
        )
        args = BubblewrapSerializer(config).serialize()
        # Find the tmpfs for /data
        found = False
        for i, arg in enumerate(args):
            if arg == "--tmpfs" and i + 1 < len(args) and args[i + 1] == "/data":
                found = True
                break
        assert found

    def test_overlay_mode_requires_source(self):
        """Overlay mode requires source to produce args."""
        config = make_config(
            overlays=[OverlayConfig(source="", dest="/data", mode="overlay")]
        )
        args = BubblewrapSerializer(config).serialize()
        # Should not have any overlay args for /data
        assert "--tmp-overlay" not in args or "/data" not in args

    def test_persistent_mode_empty_source(self):
        """Persistent mode with empty source binds write_dir directly."""
        config = make_config(
            overlays=[OverlayConfig(source="", dest="/data", mode="persistent", write_dir="/writes")]
        )
        args = BubblewrapSerializer(config).serialize()
        # Without source, should use --bind instead of --overlay
        assert "--bind" in args
        bind_idx = args.index("--bind")
        assert args[bind_idx + 1] == "/writes"
        assert args[bind_idx + 2] == "/data"
        # Should NOT have --overlay-src
        assert "--overlay-src" not in args

    def test_persistent_mode_with_source(self):
        """Persistent mode with source creates full overlay."""
        config = make_config(
            overlays=[OverlayConfig(source="/src", dest="/data", mode="persistent", write_dir="/writes")]
        )
        args = BubblewrapSerializer(config).serialize()
        assert "--overlay-src" in args
        src_idx = args.index("--overlay-src")
        assert args[src_idx + 1] == "/src"
        assert "--overlay" in args
