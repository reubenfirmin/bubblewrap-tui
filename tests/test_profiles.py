"""Tests for profile serialization and validation."""

import json
from pathlib import Path

import pytest

from model import (
    BoundDirectory,
    OverlayConfig,
    SandboxConfig,
)
from profiles import (
    Profile,
    ProfileValidationError,
    deserialize,
    serialize,
    validate_config,
)


def make_config(
    command=None,
    filesystem=None,
    network=None,
    namespace=None,
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

    # Apply namespace settings
    if namespace:
        for key, value in namespace.items():
            setattr(config.namespace, key, value)

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


class TestSerialize:
    """Test serialize() function."""

    def test_serialize_minimal_config(self, minimal_config):
        """Minimal config serializes to dict."""
        data = serialize(minimal_config)
        assert isinstance(data, dict)
        # Command is excluded from serialization
        assert "command" not in data

    def test_serialize_preserves_basic_types(self):
        """Basic types are preserved."""
        config = make_config(
            environment={
                "clear_env": True,
                "custom_hostname": "test-host",
            },
        )
        data = serialize(config)
        # The structure is now group-based, check the environment group
        assert "_environment_group" in data
        env_data = data["_environment_group"]["_values"]
        assert env_data["clear_env"] is True
        assert env_data["custom_hostname"] == "test-host"

    def test_serialize_sets_to_lists(self):
        """Sets are serialized as lists."""
        config = make_config(
            environment={"keep_env_vars": {"PATH", "HOME"}},
        )
        data = serialize(config)
        # Sets become lists
        env_data = data["_environment_group"]["_values"]
        assert isinstance(env_data["keep_env_vars"], list)
        assert set(env_data["keep_env_vars"]) == {"PATH", "HOME"}

    def test_serialize_paths_to_strings(self):
        """Paths are serialized as strings."""
        config = make_config(
            bound_dirs=[BoundDirectory(path=Path("/home/user"), readonly=True)],
        )
        data = serialize(config)
        assert isinstance(data["bound_dirs"][0]["path"], str)
        assert data["bound_dirs"][0]["path"] == "/home/user"

    def test_serialize_dicts(self):
        """Dicts are preserved."""
        config = make_config(
            environment={"custom_env_vars": {"FOO": "bar", "BAZ": "qux"}},
        )
        data = serialize(config)
        env_data = data["_environment_group"]["_values"]
        assert env_data["custom_env_vars"] == {"FOO": "bar", "BAZ": "qux"}

    def test_serialize_nested_configs(self, full_config):
        """Nested configs are serialized recursively."""
        data = serialize(full_config)
        # Check nested structures (group-based)
        assert "_vfs_group" in data
        assert "_isolation_group" in data
        assert "_process_group" in data
        assert "_environment_group" in data
        assert "_network_group" in data
        assert "_desktop_group" in data

    def test_serialize_overlays(self):
        """Overlays are serialized correctly."""
        config = make_config(
            overlays=[
                OverlayConfig(source="/src", dest="/dest", mode="tmpfs"),
                OverlayConfig(
                    source="/src2",
                    dest="/dest2",
                    mode="persistent",
                    write_dir="/writes",
                ),
            ],
        )
        data = serialize(config)
        assert len(data["overlays"]) == 2
        assert data["overlays"][0]["mode"] == "tmpfs"
        assert data["overlays"][1]["mode"] == "persistent"
        assert data["overlays"][1]["write_dir"] == "/writes"


class TestDeserialize:
    """Test deserialize() function."""

    def test_deserialize_minimal(self):
        """Deserialize minimal data."""
        data = {
            "_vfs_group": {"_values": {"dev_mode": "minimal"}},
        }
        config = deserialize(SandboxConfig, data, command=["bash"])
        assert config.command == ["bash"]
        assert config.filesystem.dev_mode == "minimal"

    def test_deserialize_sets(self):
        """Lists deserialize to sets where expected."""
        data = {
            "_environment_group": {
                "_values": {"keep_env_vars": ["PATH", "HOME"]},
            },
        }
        config = deserialize(SandboxConfig, data, command=["bash"])
        assert isinstance(config.environment.keep_env_vars, set)
        assert config.environment.keep_env_vars == {"PATH", "HOME"}

    def test_deserialize_paths(self):
        """Strings deserialize to Paths where expected."""
        data = {
            "bound_dirs": [
                {"path": "/home/user/docs", "readonly": True},
            ],
        }
        config = deserialize(SandboxConfig, data, command=["bash"])
        assert len(config.bound_dirs) == 1
        assert isinstance(config.bound_dirs[0].path, Path)
        assert config.bound_dirs[0].path == Path("/home/user/docs")

    def test_deserialize_nested_configs(self):
        """Nested configs are deserialized."""
        data = {
            "_isolation_group": {
                "_values": {
                    "unshare_user": True,
                    "unshare_ipc": True,
                },
            },
            "_process_group": {
                "_values": {
                    "uid": 1000,
                    "gid": 1000,
                },
            },
        }
        config = deserialize(SandboxConfig, data, command=["bash"])
        assert config.namespace.unshare_user is True
        assert config.namespace.unshare_ipc is True
        assert config.process.uid == 1000
        assert config.process.gid == 1000


class TestRoundTrip:
    """Test serialize -> deserialize round-trip."""

    def test_roundtrip_minimal(self, minimal_config):
        """Minimal config survives round-trip."""
        data = serialize(minimal_config)
        restored = deserialize(SandboxConfig, data, command=minimal_config.command)
        # Compare key fields
        assert restored.command == minimal_config.command

    def test_roundtrip_full(self, full_config):
        """Full config survives round-trip."""
        data = serialize(full_config)
        restored = deserialize(SandboxConfig, data, command=full_config.command)

        # Compare command
        assert restored.command == full_config.command

        # Compare filesystem
        assert restored.filesystem.dev_mode == full_config.filesystem.dev_mode
        assert restored.filesystem.mount_proc == full_config.filesystem.mount_proc
        assert restored.filesystem.mount_tmp == full_config.filesystem.mount_tmp
        assert restored.filesystem.tmpfs_size == full_config.filesystem.tmpfs_size

        # Compare namespace
        assert restored.namespace.unshare_user == full_config.namespace.unshare_user
        assert restored.namespace.unshare_pid == full_config.namespace.unshare_pid
        assert restored.namespace.unshare_ipc == full_config.namespace.unshare_ipc

        # Compare process
        assert restored.process.uid == full_config.process.uid
        assert restored.process.gid == full_config.process.gid
        assert restored.process.chdir == full_config.process.chdir

        # Compare environment
        assert restored.environment.clear_env == full_config.environment.clear_env
        assert (
            restored.environment.custom_hostname
            == full_config.environment.custom_hostname
        )
        assert (
            restored.environment.keep_env_vars == full_config.environment.keep_env_vars
        )
        assert (
            restored.environment.custom_env_vars
            == full_config.environment.custom_env_vars
        )

        # Compare bound_dirs
        assert len(restored.bound_dirs) == len(full_config.bound_dirs)
        for r, o in zip(restored.bound_dirs, full_config.bound_dirs):
            assert r.path == o.path
            assert r.readonly == o.readonly

        # Compare overlays
        assert len(restored.overlays) == len(full_config.overlays)
        for r, o in zip(restored.overlays, full_config.overlays):
            assert r.source == o.source
            assert r.dest == o.dest
            assert r.mode == o.mode
            assert r.write_dir == o.write_dir

        # Compare drop_caps
        assert restored.drop_caps == full_config.drop_caps


class TestValidateConfig:
    """Test validate_config() function."""

    def test_valid_config_no_warnings(self, minimal_config):
        """Valid minimal config produces no warnings."""
        warnings = validate_config(minimal_config)
        assert warnings == []

    def test_invalid_uid_raises(self):
        """UID outside 0-65535 raises ProfileValidationError."""
        config = make_config(process={"uid": 70000})
        with pytest.raises(ProfileValidationError) as exc_info:
            validate_config(config)
        assert "Invalid UID" in str(exc_info.value)
        assert "70000" in str(exc_info.value)

    def test_invalid_gid_raises(self):
        """GID outside 0-65535 raises ProfileValidationError."""
        config = make_config(process={"gid": -1})
        with pytest.raises(ProfileValidationError) as exc_info:
            validate_config(config)
        assert "Invalid GID" in str(exc_info.value)

    def test_valid_uid_gid_edge_cases(self):
        """Valid edge case UIDs/GIDs don't raise."""
        # UID 0 (root)
        config = make_config(process={"uid": 0, "gid": 0})
        warnings = validate_config(config)
        assert warnings == []

        # UID 65535 (max)
        config = make_config(process={"uid": 65535, "gid": 65535})
        warnings = validate_config(config)
        assert warnings == []

    def test_unknown_dev_mode_warns_and_fixes(self):
        """Unknown dev_mode produces warning and is fixed."""
        config = make_config(filesystem={"dev_mode": "invalid"})
        warnings = validate_config(config)
        assert any("dev_mode" in w for w in warnings)
        # Should be fixed to minimal
        assert config.filesystem.dev_mode == "minimal"

    def test_valid_dev_modes(self):
        """Valid dev_modes produce no warnings."""
        for mode in ["none", "minimal", "full"]:
            config = make_config(filesystem={"dev_mode": mode})
            warnings = validate_config(config)
            assert not any("dev_mode" in w for w in warnings)

    def test_unknown_overlay_mode_warns_and_fixes(self):
        """Unknown overlay mode produces warning and is fixed."""
        config = make_config(
            overlays=[OverlayConfig(source="/src", dest="/dest", mode="invalid")],
        )
        warnings = validate_config(config)
        assert any("unknown mode" in w for w in warnings)
        assert config.overlays[0].mode == "tmpfs"

    def test_persistent_overlay_without_write_dir_warns(self):
        """Persistent overlay without write_dir produces warning."""
        config = make_config(
            overlays=[
                OverlayConfig(source="/src", dest="/dest", mode="persistent", write_dir="")
            ],
        )
        warnings = validate_config(config)
        assert any("write_dir" in w for w in warnings)

    def test_nonexistent_bound_dir_warns(self, tmp_path):
        """Non-existent bound directory produces warning."""
        nonexistent = tmp_path / "does_not_exist"
        config = make_config(
            bound_dirs=[BoundDirectory(path=nonexistent, readonly=True)],
        )
        warnings = validate_config(config)
        assert any("does not exist" in w for w in warnings)

    def test_existing_bound_dir_no_warning(self, tmp_path):
        """Existing bound directory produces no warning."""
        existing = tmp_path / "exists"
        existing.mkdir()
        config = make_config(
            bound_dirs=[BoundDirectory(path=existing, readonly=True)],
        )
        warnings = validate_config(config)
        # Should have no warnings about the existing directory
        assert not any("does not exist" in w for w in warnings)


class TestProfile:
    """Test Profile class."""

    def test_profile_name(self, tmp_profile):
        """Profile name is the filename stem."""
        profile_path = tmp_profile / "my-profile.json"
        profile = Profile(profile_path)
        assert profile.name == "my-profile"

    def test_save_and_load(self, tmp_profile, minimal_config):
        """Profile can be saved and loaded."""
        profile_path = tmp_profile / "test.json"
        profile = Profile(profile_path)

        # Save
        profile.save(minimal_config)
        assert profile_path.exists()

        # Load
        loaded, warnings = profile.load(["bash"])
        assert loaded.command == ["bash"]
        assert warnings == []

    def test_save_creates_parent_dirs(self, tmp_path):
        """Save creates parent directories if needed."""
        deep_path = tmp_path / "a" / "b" / "c" / "profile.json"
        profile = Profile(deep_path)
        config = SandboxConfig(command=["bash"])
        profile.save(config)
        assert deep_path.exists()

    def test_load_with_different_command(self, tmp_profile, full_config):
        """Load uses provided command, not saved one."""
        profile_path = tmp_profile / "test.json"
        profile = Profile(profile_path)
        profile.save(full_config)

        # Load with different command
        loaded, _ = profile.load(["different", "command"])
        assert loaded.command == ["different", "command"]

    def test_load_validates(self, tmp_profile):
        """Load validates the config."""
        profile_path = tmp_profile / "invalid.json"
        # Write invalid JSON directly
        data = {
            "_process_group": {"_values": {"uid": 999999}},  # Invalid UID
        }
        profile_path.write_text(json.dumps(data))

        profile = Profile(profile_path)
        with pytest.raises(ProfileValidationError):
            profile.load(["bash"])

    def test_delete(self, tmp_profile, minimal_config):
        """Profile can be deleted."""
        profile_path = tmp_profile / "to-delete.json"
        profile = Profile(profile_path)
        profile.save(minimal_config)
        assert profile_path.exists()

        profile.delete()
        assert not profile_path.exists()

    def test_list_profiles(self, tmp_profile, minimal_config):
        """List profiles in directory."""
        # Create some profiles
        for name in ["profile-a", "profile-b", "profile-c"]:
            Profile(tmp_profile / f"{name}.json").save(minimal_config)

        profiles = Profile.list_profiles(tmp_profile)
        names = [p.name for p in profiles]
        assert "profile-a" in names
        assert "profile-b" in names
        assert "profile-c" in names

    def test_list_profiles_empty_dir(self, tmp_path):
        """List profiles returns empty for empty dir."""
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()
        profiles = Profile.list_profiles(empty_dir)
        assert profiles == []

    def test_list_profiles_nonexistent_dir(self, tmp_path):
        """List profiles returns empty for nonexistent dir."""
        nonexistent = tmp_path / "does_not_exist"
        profiles = Profile.list_profiles(nonexistent)
        assert profiles == []

    def test_list_profiles_sorted(self, tmp_profile, minimal_config):
        """List profiles returns sorted by name."""
        for name in ["zebra", "alpha", "middle"]:
            Profile(tmp_profile / f"{name}.json").save(minimal_config)

        profiles = Profile.list_profiles(tmp_profile)
        names = [p.name for p in profiles]
        assert names == sorted(names)
