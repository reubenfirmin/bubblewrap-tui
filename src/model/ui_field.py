"""UIField descriptor for config classes with UI and bwrap metadata."""

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
