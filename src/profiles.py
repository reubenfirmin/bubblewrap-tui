"""Profile serialization for bui."""

from __future__ import annotations

import json
import logging
from dataclasses import fields, is_dataclass
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, get_args, get_origin, get_type_hints

log = logging.getLogger(__name__)

from constants import MAX_UID_GID
from model import BoundDirectory, OverlayConfig, SandboxConfig
from model.config_group import ConfigGroup
from model.ui_field import ConfigBase, Field, UIField


class ProfileValidationError(Exception):
    """Raised when profile validation fails."""


def validate_config(config: SandboxConfig, profile_name: str | None = None) -> list[str]:
    """Validate a SandboxConfig and return list of warnings.

    Args:
        config: The SandboxConfig to validate
        profile_name: Optional profile name for context in error messages

    Raises ProfileValidationError for critical issues.
    Returns list of non-critical warnings.
    """
    warnings = []
    prefix = f"Profile '{profile_name}': " if profile_name else ""

    # Validate UID/GID range (0-65535)
    if config.user.uid is not None:
        if not (0 <= config.user.uid <= MAX_UID_GID):
            raise ProfileValidationError(
                f"{prefix}Invalid UID: {config.user.uid} (must be 0-{MAX_UID_GID})"
            )

    if config.user.gid is not None:
        if not (0 <= config.user.gid <= MAX_UID_GID):
            raise ProfileValidationError(
                f"{prefix}Invalid GID: {config.user.gid} (must be 0-{MAX_UID_GID})"
            )

    # Validate dev_mode is a known value
    valid_dev_modes = {"none", "minimal", "full"}
    if config.vfs.dev_mode not in valid_dev_modes:
        warnings.append(
            f"Unknown dev_mode '{config.vfs.dev_mode}', defaulting to 'minimal'"
        )
        config.vfs.dev_mode = "minimal"

    # Validate overlay configs
    for i, overlay in enumerate(config.overlays):
        if overlay.mode not in ("tmpfs", "persistent"):
            warnings.append(f"Overlay {i}: unknown mode '{overlay.mode}', using 'tmpfs'")
            overlay.mode = "tmpfs"
        if overlay.mode == "persistent" and not overlay.write_dir:
            warnings.append(f"Overlay {i}: persistent mode requires write_dir")
        if overlay.mode == "persistent" and overlay.write_dir:
            # Check for conflicting paths - these are critical misconfigs
            src = Path(overlay.source).resolve() if overlay.source else None
            dest = Path(overlay.dest).resolve() if overlay.dest else None
            write = Path(overlay.write_dir).resolve()
            if src and write == src:
                raise ProfileValidationError(
                    f"Overlay {i}: write_dir cannot be same as source"
                )
            if dest and write == dest:
                raise ProfileValidationError(
                    f"Overlay {i}: write_dir cannot be same as mount point"
                )

    # Warn about non-existent bound directories (don't fail - they might be created later)
    for bd in config.bound_dirs:
        if not bd.path.exists():
            warnings.append(f"Bound directory does not exist: {bd.path}")

    # Warn about VFS conflicts
    for bd in config.bound_dirs:
        resolved = bd.path.resolve()
        if resolved == Path("/proc") and config.vfs.mount_proc:
            warnings.append("/proc bound directory conflicts with VFS /proc option")
        if resolved == Path("/tmp") and config.vfs.mount_tmp:
            warnings.append("/tmp bound directory conflicts with VFS /tmp option")

    return warnings

if TYPE_CHECKING:
    from textual.app import App

# Default profiles directory
BUI_PROFILES_DIR = Path.home() / ".config" / "bui" / "profiles"

# Fields to exclude from profile serialization
# _system_paths_group is UI-only state - checkbox values are derived from bound_dirs
EXCLUDE_FIELDS = {"command", "_system_paths_group"}


def _has_ui_fields(obj: Any) -> bool:
    """Check if an object uses UIField/Field descriptors."""
    cls = obj if isinstance(obj, type) else type(obj)
    return hasattr(cls, "_ui_fields") or hasattr(cls, "_data_fields")


def _get_all_fields(cls: type) -> dict[str, UIField | Field]:
    """Get all UIField and Field descriptors from a class."""
    result = {}
    if hasattr(cls, "_ui_fields"):
        result.update(cls._ui_fields)
    if hasattr(cls, "_data_fields"):
        result.update(cls._data_fields)
    return result


def serialize(obj: Any) -> dict | list | str | int | float | bool | None:
    """Recursively serialize a config object to JSON-compatible dict."""
    # Handle ConfigGroup objects - only serialize their _values
    if isinstance(obj, ConfigGroup):
        return {"_values": serialize(obj._values)}

    # Handle UIField-based classes
    if _has_ui_fields(obj) and not isinstance(obj, type):
        result = {}
        for name, field in _get_all_fields(type(obj)).items():
            if name in EXCLUDE_FIELDS:
                continue
            value = getattr(obj, name)
            result[name] = serialize(value)
        return result

    # Handle dataclasses (for BoundDirectory, OverlayConfig, SandboxConfig)
    if is_dataclass(obj) and not isinstance(obj, type):
        result = {}
        for f in fields(obj):
            if f.name in EXCLUDE_FIELDS:
                continue
            value = getattr(obj, f.name)
            result[f.name] = serialize(value)
        return result

    # Handle other types
    if isinstance(obj, Enum):
        return obj.value
    if isinstance(obj, Path):
        return str(obj)
    if isinstance(obj, set):
        return list(obj)
    if isinstance(obj, list):
        return [serialize(v) for v in obj]
    if isinstance(obj, dict):
        return {k: serialize(v) for k, v in obj.items()}
    return obj


def deserialize(cls: type, data: dict, **overrides) -> Any:
    """Deserialize a dict into a config instance."""
    # Handle SandboxConfig specially to restore group values
    if cls is SandboxConfig:
        config = _deserialize_sandbox_config(data, **overrides)
        return config

    # Handle UIField-based classes
    if hasattr(cls, "_ui_fields") or hasattr(cls, "_data_fields"):
        kwargs = {}
        all_fields = _get_all_fields(cls)

        for name, field in all_fields.items():
            if name in overrides:
                kwargs[name] = overrides[name]
                continue
            if name not in data:
                continue

            value = data[name]
            kwargs[name] = _deserialize_field_value(value, field)

        return cls(**kwargs)

    # Handle dataclasses
    if is_dataclass(cls):
        hints = get_type_hints(cls)
        kwargs = {}

        for f in fields(cls):
            if f.name in overrides:
                kwargs[f.name] = overrides[f.name]
                continue
            if f.name not in data:
                continue

            value = data[f.name]
            field_type = hints.get(f.name)
            kwargs[f.name] = _deserialize_value(value, field_type)

        return cls(**kwargs)

    raise ValueError(f"Cannot deserialize {cls}")


def _deserialize_field_value(value: Any, field: UIField | Field) -> Any:
    """Deserialize a value based on a UIField/Field's type."""
    if value is None:
        return None

    field_type = field.type_

    # Handle set
    if field_type == set:
        return set(value) if value else set()

    # Handle dict
    if field_type == dict:
        return value if value else {}

    # Handle Path
    if field_type == Path:
        return Path(value)

    # Handle nested UIField-based class
    if hasattr(field_type, "_ui_fields") or hasattr(field_type, "_data_fields"):
        return deserialize(field_type, value)

    # Handle nested dataclass
    if is_dataclass(field_type):
        return deserialize(field_type, value)

    return value


def _deserialize_value(value: Any, field_type: type) -> Any:
    """Deserialize a value based on its type hint (for dataclasses)."""
    if value is None:
        return None

    origin = get_origin(field_type)
    args = get_args(field_type)

    # Handle Enum types
    if field_type is not None and isinstance(field_type, type) and issubclass(field_type, Enum):
        return field_type(value)

    # Handle ConfigGroup - don't deserialize here, handled specially in SandboxConfig
    if field_type is ConfigGroup:
        return None  # Will be reconstructed by SandboxConfig.__post_init__

    # Handle list[X]
    if origin is list and args:
        item_type = args[0]
        if is_dataclass(item_type):
            return [deserialize(item_type, v) for v in value]
        if _has_ui_fields(item_type):
            return [deserialize(item_type, v) for v in value]
        if item_type is Path:
            return [Path(v) for v in value]
        return value

    # Handle set[X]
    if origin is set:
        return set(value)

    # Handle Path
    if field_type is Path:
        return Path(value)

    # Handle nested dataclass
    if is_dataclass(field_type):
        return deserialize(field_type, value)

    # Handle nested UIField-based class
    if _has_ui_fields(field_type):
        return deserialize(field_type, value)

    return value


class Profile:
    """Handles saving and loading sandbox profiles."""

    def __init__(self, path: Path):
        self.path = path

    @property
    def name(self) -> str:
        """Get the profile name (filename without extension)."""
        return self.path.stem

    def save(self, config: SandboxConfig) -> None:
        """Save config to profile file."""
        data = serialize(config)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(data, indent=2))

    def load(self, command: list[str]) -> tuple[SandboxConfig, list[str]]:
        """Load profile and create config with given command.

        Returns:
            Tuple of (config, warnings) where warnings is a list of non-critical issues.

        Raises:
            ProfileValidationError: For critical validation failures.
        """
        data = json.loads(self.path.read_text())
        config = deserialize(SandboxConfig, data, command=command)
        warnings = validate_config(config, profile_name=self.name)
        return config, warnings

    def delete(self) -> None:
        """Delete the profile file."""
        self.path.unlink()

    @classmethod
    def list_profiles(cls, directory: Path) -> list["Profile"]:
        """List all profiles in a directory."""
        if not directory.exists():
            return []
        return [cls(p) for p in sorted(directory.glob("*.json"))]


def _deserialize_sandbox_config(data: dict, **overrides) -> SandboxConfig:
    """Deserialize a SandboxConfig from data."""
    hints = get_type_hints(SandboxConfig)
    kwargs = {}

    for f in fields(SandboxConfig):
        if f.name in overrides:
            kwargs[f.name] = overrides[f.name]
            continue
        if f.name not in data:
            continue
        # Skip group fields - they'll be restored separately
        if f.name.startswith("_") and f.name.endswith("_group"):
            continue

        value = data[f.name]
        field_type = hints.get(f.name)
        kwargs[f.name] = _deserialize_value(value, field_type)

    config = SandboxConfig(**kwargs)
    _restore_group_values(config, data)
    return config


def _restore_group_values(config: SandboxConfig, data: dict) -> None:
    """Restore ConfigGroup values from serialized data."""
    # Note: _system_paths_group is NOT restored - it's UI-only state
    # Checkbox states are derived from bound_dirs when loading a profile
    group_fields = [
        ("_vfs_group", config._vfs_group),
        ("_user_group", config._user_group),
        ("_isolation_group", config._isolation_group),
        ("_hostname_group", config._hostname_group),
        ("_process_group", config._process_group),
        ("_network_group", config._network_group),
        ("_desktop_group", config._desktop_group),
        ("_environment_group", config._environment_group),
    ]

    for field_name, group in group_fields:
        if field_name in data and isinstance(data[field_name], dict):
            group_data = data[field_name]
            if "_values" in group_data:
                for key, value in group_data["_values"].items():
                    # Handle sets (serialized as lists)
                    if isinstance(value, list) and key in ("keep_env_vars", "unset_env_vars"):
                        value = set(value)
                    group.set(key, value)


class ProfileManager:
    """Manages profile UI operations for the app."""

    def __init__(
        self,
        app: App,
        get_config: Callable[[], SandboxConfig],
        set_config: Callable[[SandboxConfig], None],
        on_status: Callable[[str], None],
        on_config_loaded: Callable[[], None],
        profiles_dir: Path = BUI_PROFILES_DIR,
    ):
        """Initialize the profile manager.

        Args:
            app: The Textual app instance
            get_config: Callback to get the current config
            set_config: Callback to set a new config
            on_status: Callback to display status messages
            on_config_loaded: Callback when a profile is loaded (to sync UI)
            profiles_dir: Directory for profile storage
        """
        self.app = app
        self._get_config = get_config
        self._set_config = set_config
        self._on_status = on_status
        self._on_config_loaded = on_config_loaded
        self.profiles_dir = profiles_dir

    def refresh_profiles_list(self, profile_item_class: type) -> None:
        """Refresh the list of saved profiles.

        Args:
            profile_item_class: The ProfileItem widget class
        """
        from textual.containers import VerticalScroll
        from textual.css.query import NoMatches

        from ui.ids import css
        import ui.ids as ids

        try:
            profiles_list = self.app.query_one(css(ids.PROFILES_LIST), VerticalScroll)
            # Clear existing items
            for item in list(profiles_list.query(profile_item_class)):
                item.remove()
            # Load profiles from directory
            for profile in Profile.list_profiles(self.profiles_dir):
                profiles_list.mount(
                    profile_item_class(profile.path, self.load_profile, self.delete_profile)
                )
        except NoMatches:
            log.debug("Profiles list not found")

    def load_profile(self, profile_path: Path) -> None:
        """Load a profile from file."""
        try:
            config = self._get_config()
            profile = Profile(profile_path)
            new_config, warnings = profile.load(config.command)
            self._set_config(new_config)
            self._on_config_loaded()
            # Show warnings if any, otherwise success message
            if warnings:
                self._on_status(f"Loaded {profile.name} ({len(warnings)} warning(s))")
            else:
                self._on_status(f"Loaded profile: {profile.name}")
        except ProfileValidationError as e:
            self._on_status(f"Profile invalid: {e}")
        except Exception as e:
            self._on_status(f"Error loading profile: {e}")

    def delete_profile(self, item: Any) -> None:
        """Delete a profile.

        Args:
            item: ProfileItem widget instance with profile_path attribute
        """
        try:
            profile = Profile(item.profile_path)
            profile.delete()
            item.remove()
            self._on_status(f"Deleted profile: {profile.name}")
        except Exception as e:
            self._on_status(f"Error deleting profile: {e}")

    def save_profile(self, name: str, sync_config: Callable[[], None]) -> None:
        """Save current config as a profile.

        Args:
            name: Profile name
            sync_config: Callback to sync config from UI before saving
        """
        if not name:
            self._on_status("Enter a profile name")
            return
        # Sync config from UI first
        sync_config()
        # Save to file
        profile = Profile(self.profiles_dir / f"{name}.json")
        profile.save(self._get_config())
        self._on_status(f"Saved profile: {name}")
