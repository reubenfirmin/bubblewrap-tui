"""Sandbox configuration model.

Uses the group-based architecture while providing backward-compatible
property access for existing code.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any

from model.bound_directory import BoundDirectory
from model.config_group import ConfigGroup
from model.network_filter import NetworkFilter
from model.overlay_config import OverlayConfig


class GroupProxy:
    """Proxy that provides attribute access to a ConfigGroup's values.

    **Why this pattern exists:**
    The application uses ConfigGroup instances to organize settings into logical
    groups (filesystem, user, network, etc.). Each group stores its values in a
    _values dict. However, existing code uses attribute-style access like
    `config.filesystem.mount_proc` for readability.

    **How it works:**
    GroupProxy wraps a ConfigGroup and intercepts __getattr__/__setattr__ to
    redirect attribute access to the underlying group's _values dict.

    For example:
        config.filesystem.mount_proc  # Reads _values["mount_proc"] from vfs_group
        config.user.uid = 1000        # Writes to _values["uid"] in user_group

    **How to use:**
    - Read: `value = config.network.share_net`
    - Write: `config.network.share_net = True`
    - Access raw group: `config._network_group` (for serialization, iteration)

    Subclasses (FilesystemProxy, NamespaceProxy, etc.) may span multiple groups
    or add special behavior.
    """

    def __init__(self, group: ConfigGroup) -> None:
        object.__setattr__(self, "_group", group)

    def __getattr__(self, name: str) -> Any:
        group = object.__getattribute__(self, "_group")
        # Check if it's an item in the group
        if name in group._values:
            return group._values[name]
        # Check if it's a group attribute
        if hasattr(group, name):
            return getattr(group, name)
        raise AttributeError(f"'{type(self).__name__}' has no attribute '{name}'")

    def __setattr__(self, name: str, value: Any) -> None:
        group = object.__getattribute__(self, "_group")
        group._values[name] = value

    @classmethod
    def get_ui_fields(cls) -> dict:
        """For compatibility with code that uses ClassName.get_ui_fields()."""
        return {}


class FilesystemProxy(GroupProxy):
    """Proxy for filesystem settings, spanning vfs and system_paths groups."""

    def __init__(self, vfs_group: ConfigGroup, system_paths_group: ConfigGroup) -> None:
        object.__setattr__(self, "_vfs_group", vfs_group)
        object.__setattr__(self, "_system_paths_group", system_paths_group)

    def __getattr__(self, name: str) -> Any:
        vfs = object.__getattribute__(self, "_vfs_group")
        syspaths = object.__getattribute__(self, "_system_paths_group")

        # Check vfs group first
        if name in vfs._values:
            return vfs._values[name]
        # Check system_paths group
        if name in syspaths._values:
            return syspaths._values[name]
        raise AttributeError(f"'{type(self).__name__}' has no attribute '{name}'")

    def __setattr__(self, name: str, value: Any) -> None:
        vfs = object.__getattribute__(self, "_vfs_group")
        syspaths = object.__getattribute__(self, "_system_paths_group")

        if name in ("dev_mode", "mount_proc", "mount_tmp", "tmpfs_size"):
            vfs._values[name] = value
        else:
            syspaths._values[name] = value


class NamespaceProxy(GroupProxy):
    """Proxy for namespace isolation settings."""

    # Class-level attribute for summary lookup (used by _add_namespace_summary)
    unshare_pid = property(lambda self: object.__getattribute__(self, "_group").get_item("unshare_pid"))


class ProcessProxy(GroupProxy):
    """Proxy for process settings with uid/gid defaults."""


class EnvironmentProxy(GroupProxy):
    """Proxy for environment settings."""


@dataclass
class SandboxConfig:
    """Configuration for the sandbox.

    This class uses the group-based architecture internally while providing
    a backward-compatible API through property accessors.
    """

    command: list[str] = field(default_factory=list)
    bound_dirs: list[BoundDirectory] = field(default_factory=list)
    overlays: list[OverlayConfig] = field(default_factory=list)
    network_filter: NetworkFilter = field(default_factory=NetworkFilter)
    drop_caps: set[str] = field(default_factory=set)

    # Internal group storage
    _vfs_group: ConfigGroup = field(default=None, repr=False)
    _system_paths_group: ConfigGroup = field(default=None, repr=False)
    _user_group: ConfigGroup = field(default=None, repr=False)
    _isolation_group: ConfigGroup = field(default=None, repr=False)
    _process_group: ConfigGroup = field(default=None, repr=False)
    _network_group: ConfigGroup = field(default=None, repr=False)
    _desktop_group: ConfigGroup = field(default=None, repr=False)
    _environment_group: ConfigGroup = field(default=None, repr=False)

    def __post_init__(self) -> None:
        """Initialize groups with fresh copies."""
        # Import here to avoid circular imports (stripped in concatenated build)
        from model import groups

        # Create deep copies of groups so each SandboxConfig is independent
        if self._vfs_group is None:
            self._vfs_group = _copy_group(groups.vfs_group)
        if self._system_paths_group is None:
            self._system_paths_group = _copy_group(groups.system_paths_group)
        if self._user_group is None:
            self._user_group = _copy_group(groups.user_group)
        if self._isolation_group is None:
            self._isolation_group = _copy_group(groups.isolation_group)
        if self._process_group is None:
            self._process_group = _copy_group(groups.process_group)
        if self._network_group is None:
            self._network_group = _copy_group(groups.network_group)
        if self._desktop_group is None:
            self._desktop_group = _copy_group(groups.desktop_group)
        if self._environment_group is None:
            self._environment_group = _copy_group(groups.environment_group)
            # Reset mutable defaults
            self._environment_group.set("keep_env_vars", set())
            self._environment_group.set("unset_env_vars", set())
            self._environment_group.set("custom_env_vars", {})

    # Property accessors for backward compatibility
    @property
    def filesystem(self) -> FilesystemProxy:
        """Access filesystem settings."""
        return FilesystemProxy(self._vfs_group, self._system_paths_group)

    @property
    def user(self) -> GroupProxy:
        """Access user identity settings (unshare_user, uid, gid, username)."""
        return GroupProxy(self._user_group)

    @property
    def namespace(self) -> GroupProxy:
        """Access namespace isolation settings (PID, IPC, UTS, cgroup)."""
        return NamespaceProxy(self._isolation_group)

    @property
    def process(self) -> GroupProxy:
        """Access process settings."""
        return ProcessProxy(self._process_group)

    @property
    def network(self) -> GroupProxy:
        """Access network settings."""
        return GroupProxy(self._network_group)

    @property
    def desktop(self) -> GroupProxy:
        """Access desktop integration settings."""
        return GroupProxy(self._desktop_group)

    @property
    def environment(self) -> GroupProxy:
        """Access environment settings."""
        return GroupProxy(self._environment_group)

    def get_all_groups(self) -> list[ConfigGroup]:
        """Get all groups in serialization order."""
        return [
            self._vfs_group,
            self._system_paths_group,
            self._user_group,
            self._isolation_group,
            self._process_group,
            self._network_group,
            self._desktop_group,
            self._environment_group,
        ]

    def build_command(self, fd_map: dict[str, int] | None = None) -> list[str]:
        """Build the complete bwrap command.

        Args:
            fd_map: Optional mapping of dest_path -> FD number for virtual user files

        Note:
            TODO: Consider dependency injection for testability.
            Currently tightly coupled to BubblewrapSerializer for simplicity.
        """
        from bwrap import BubblewrapSerializer
        return BubblewrapSerializer(self).serialize(fd_map)

    def get_virtual_user_data(self) -> list[tuple[str, str]]:
        """Get virtual user file data that needs to be passed via FDs.

        Returns list of (content, dest_path) tuples for files to inject.
        """
        from bwrap import BubblewrapSerializer
        return BubblewrapSerializer(self).get_virtual_user_data()

    def get_explanation(self) -> str:
        """Generate a human-readable explanation of the sandbox."""
        from bwrap import BubblewrapSummarizer
        return BubblewrapSummarizer(self).summarize()


def _copy_group(group: ConfigGroup) -> ConfigGroup:
    """Create a deep copy of a ConfigGroup."""
    new_group = ConfigGroup(
        name=group.name,
        title=group.title,
        items=group.items,  # Items are shared (they're definitions, not data)
        description=group.description,
        _to_args_fn=group._to_args_fn,
        _to_summary_fn=group._to_summary_fn,
    )
    # Deep copy the values dict
    new_group._values = copy.deepcopy(group._values)
    return new_group
