"""UIField descriptor for config classes with UI and bwrap metadata.

This module implements Python's descriptor protocol to create fields that:
1. Store configuration values (like regular instance attributes)
2. Carry UI metadata (widget IDs, labels, explanations)
3. Know how to generate bwrap command-line arguments

The Descriptor Pattern
----------------------
Python descriptors are objects that define __get__, __set__, and optionally
__delete__ methods. When a descriptor is assigned to a class attribute, Python
intercepts attribute access and delegates to these methods.

This pattern solves a key problem: we need configuration fields that are both
data containers AND metadata containers. A naive approach would require
separate dictionaries mapping field names to metadata, leading to maintenance
headaches and potential mismatches.

Architecture Overview
---------------------
                    ┌─────────────────┐
                    │  ConfigBase     │  Base class providing __init__,
                    │                 │  to_bwrap_args(), get_*_fields()
                    └────────┬────────┘
                             │
         ┌───────────────────┼───────────────────┐
         │                   │                   │
         ▼                   ▼                   ▼
┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐
│ FilesystemConfig│ │ NamespaceConfig │ │ NetworkConfig   │
│                 │ │                 │ │                 │
│ mount_proc=...  │ │ unshare_user=...│ │ share_net=...   │
│ mount_tmp=...   │ │ unshare_pid=... │ │ bind_resolv=... │
└─────────────────┘ └─────────────────┘ └─────────────────┘
        │                   │                   │
        └───────────────────┴───────────────────┘
                            │
                  Uses UIField/Field descriptors

UIField vs Field
----------------
- UIField: For config options that have a corresponding UI widget (checkbox/input)
  Contains: type, default, checkbox_id, label, explanation, bwrap_flag/bwrap_args

- Field: For data-only fields (no UI representation but still serialized)
  Contains: type, default/default_factory, bwrap_args

Usage Examples
--------------
Defining a config class with UIField:

    class NamespaceConfig(ConfigBase):
        unshare_user = UIField(
            type_=bool,
            default=True,
            checkbox_id="opt-unshare-user",
            label="User namespace",
            explanation="Isolate user/group IDs",
            bwrap_flag="--unshare-user",
        )

Using the config:

    config = NamespaceConfig()
    config.unshare_user = True        # Set value
    print(config.unshare_user)        # Get value: True

    # Access metadata (via class, not instance)
    field = NamespaceConfig.unshare_user
    print(field.checkbox_id)          # "opt-unshare-user"
    print(field.explanation)          # "Isolate user/group IDs"

    # Generate bwrap args
    args = config.to_bwrap_args()     # ["--unshare-user"]

Complex bwrap args with a callable:

    chdir = UIField(
        type_=str,
        default="",
        checkbox_id="opt-chdir",
        label="Working directory",
        explanation="Set working directory inside sandbox",
        bwrap_args=lambda v: ["--chdir", v] if v else [],
    )

Using Field for data-only (mutable default with factory):

    class EnvironmentConfig(ConfigBase):
        keep_env_vars = Field(
            type_=set,
            default_factory=set,  # Creates new set per instance
        )

Integration Points
------------------
1. ConfigSyncManager (controller/sync.py): Uses checkbox_id to find widgets,
   syncs values bidirectionally between UI and config.

2. Profile serialization (profiles.py): Iterates _ui_fields and _data_fields
   to serialize/deserialize configs to JSON.

3. Command building (model/__init__.py): Calls to_bwrap_args() on each
   config section to build the final bwrap command.

4. UI composition (ui/compose.py): Uses UIField metadata to create OptionCard
   widgets with correct labels, IDs, and explanations.
"""

from pathlib import Path
from typing import Any, Callable


class UIField:
    """Descriptor that holds field value + all metadata.

    When accessed on the class, returns the UIField itself (with metadata).
    When accessed on an instance, returns the actual value.
    """

    def __init__(
        self,
        type_: type,
        default: Any,
        checkbox_id: str,
        label: str,
        explanation: str,
        *,
        bwrap_flag: str | None = None,
        bwrap_args: Callable[[Any], list[str]] | None = None,
        summary: str | None = None,
    ):
        """Create a UIField descriptor.

        Args:
            type_: The Python type of this field (bool, str, int, etc.)
            default: Default value for the field
            checkbox_id: The Textual widget ID for this field's checkbox
            label: Short label for UI checkbox
            explanation: Explanation text shown below checkbox
            bwrap_flag: Simple bwrap flag (e.g., "--unshare-user") - used when value is truthy
            bwrap_args: Callable that takes value and returns bwrap args list (for complex cases)
            summary: Text for summary view (defaults to explanation)
        """
        self.type_ = type_
        self.default = default
        self.checkbox_id = checkbox_id
        self.label = label
        self.explanation = explanation
        self.bwrap_flag = bwrap_flag
        self.bwrap_args = bwrap_args
        self.summary = summary or explanation
        self.name: str | None = None

    def __set_name__(self, owner: type, name: str) -> None:
        """Called when the descriptor is assigned to a class attribute."""
        self.name = name
        # Register field with owner class
        if not hasattr(owner, "_ui_fields"):
            owner._ui_fields = {}
        owner._ui_fields[name] = self

    def __get__(self, obj: Any, owner: type | None = None) -> Any:
        """Get the field value or the descriptor itself.

        - Class access (obj is None): returns UIField with metadata
        - Instance access: returns the actual value
        """
        if obj is None:
            return self
        return obj.__dict__.get(self.name, self.default)

    def __set__(self, obj: Any, value: Any) -> None:
        """Set the field value on an instance."""
        obj.__dict__[self.name] = value

    def to_bwrap_args(self, value: Any) -> list[str]:
        """Generate bwrap command-line args for this field's value.

        Args:
            value: The current value of this field

        Returns:
            List of bwrap arguments (may be empty)
        """
        if self.bwrap_args:
            return self.bwrap_args(value)
        if self.bwrap_flag and value:
            return [self.bwrap_flag]
        return []


class Field:
    """Descriptor for data-only fields (no UI, but still serialized)."""

    def __init__(
        self,
        type_: type,
        default: Any = None,
        *,
        default_factory: Callable[[], Any] | None = None,
        bwrap_args: Callable[[Any], list[str]] | None = None,
    ):
        """Create a data field descriptor.

        Args:
            type_: The Python type of this field
            default: Default value (use None with default_factory for mutable defaults)
            default_factory: Factory function for mutable defaults (set, list, dict)
            bwrap_args: Callable that takes value and returns bwrap args list
        """
        self.type_ = type_
        self.default = default
        self.default_factory = default_factory
        self.bwrap_args = bwrap_args
        self.name: str | None = None

    def __set_name__(self, owner: type, name: str) -> None:
        self.name = name
        if not hasattr(owner, "_data_fields"):
            owner._data_fields = {}
        owner._data_fields[name] = self

    def __get__(self, obj: Any, owner: type | None = None) -> Any:
        if obj is None:
            return self
        if self.name not in obj.__dict__:
            if self.default_factory:
                obj.__dict__[self.name] = self.default_factory()
            else:
                return self.default
        return obj.__dict__[self.name]

    def __set__(self, obj: Any, value: Any) -> None:
        obj.__dict__[self.name] = value

    def to_bwrap_args(self, value: Any) -> list[str]:
        if self.bwrap_args:
            return self.bwrap_args(value)
        return []


class ConfigBase:
    """Base class for UIField-based config classes."""

    _ui_fields: dict[str, UIField]
    _data_fields: dict[str, Field]

    def __init__(self, **kwargs: Any) -> None:
        """Initialize config with optional field values."""
        all_fields = {**self.get_ui_fields(), **self.get_data_fields()}
        for name, value in kwargs.items():
            if name in all_fields:
                setattr(self, name, value)

    @classmethod
    def get_ui_fields(cls) -> dict[str, UIField]:
        """Get all UIField descriptors for this class."""
        return getattr(cls, "_ui_fields", {})

    @classmethod
    def get_data_fields(cls) -> dict[str, Field]:
        """Get all data Field descriptors for this class."""
        return getattr(cls, "_data_fields", {})

    @classmethod
    def get_all_fields(cls) -> dict[str, UIField | Field]:
        """Get all fields (UI and data) for this class."""
        return {**cls.get_ui_fields(), **cls.get_data_fields()}

    def to_bwrap_args(self) -> list[str]:
        """Generate all bwrap args for this config section."""
        args = []
        for name, field in self.get_all_fields().items():
            value = getattr(self, name)
            args.extend(field.to_bwrap_args(value))
        return args
