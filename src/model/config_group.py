"""ConfigGroup: the fundamental unit of configuration.

Each group:
- Contains related settings (items)
- Maps to one UI card/section
- Maps to one summary bullet
- Gets one color in command/summary
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    from model.ui_field import UIField


@dataclass
class ConfigGroup:
    """A group of related configuration settings.

    This is the fundamental unit of configuration that maps to:
    - One UI section/card
    - One summary bullet
    - One color in command/summary display
    """

    name: str  # identifier (e.g., "system_paths")
    title: str  # UI section label (e.g., "System Paths (read-only)")
    items: list[UIField] = field(default_factory=list)
    description: str = ""  # optional multi-line hint text

    # Storage for actual values (maps item name -> value)
    _values: dict[str, Any] = field(default_factory=dict, repr=False)

    # Optional custom serialization function for complex groups
    _to_args_fn: Callable[[ConfigGroup], list[str]] | None = field(default=None, repr=False)

    # Optional custom summary function for complex groups
    _to_summary_fn: Callable[[ConfigGroup], str | None] | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        """Initialize default values from items."""
        for item in self.items:
            if item.name not in self._values:
                self._values[item.name] = item.default

    def get(self, name: str) -> Any:
        """Get a field value by name."""
        return self._values.get(name)

    def set(self, name: str, value: Any) -> None:
        """Set a field value by name."""
        self._values[name] = value

    def __getattr__(self, name: str) -> Any:
        """Allow attribute access to field values."""
        if name.startswith("_") or name in ("name", "title", "items", "description"):
            raise AttributeError(name)
        if "_values" in self.__dict__ and name in self._values:
            return self._values[name]
        raise AttributeError(f"'{type(self).__name__}' has no attribute '{name}'")

    def __setattr__(self, name: str, value: Any) -> None:
        """Allow attribute setting for field values."""
        if name in ("name", "title", "items", "description", "_values", "_to_args_fn", "_to_summary_fn"):
            object.__setattr__(self, name, value)
        elif "_values" in self.__dict__:
            self._values[name] = value
        else:
            object.__setattr__(self, name, value)

    def to_args(self) -> list[str]:
        """Collect bwrap args from all items."""
        if self._to_args_fn:
            return self._to_args_fn(self)

        args = []
        for item in self.items:
            value = self._values.get(item.name, item.default)
            args.extend(item.to_bwrap_args(value))
        return args

    def to_summary(self) -> str | None:
        """Generate summary bullet for this group.

        Returns None if the group has nothing to summarize.
        """
        if self._to_summary_fn:
            return self._to_summary_fn(self)

        # Default: list items that have non-default truthy values
        active = []
        for item in self.items:
            value = self._values.get(item.name, item.default)
            if value and value != item.default:
                active.append(item.label)
        if active:
            return f"• {self.title}: {', '.join(active)}"
        return None

    @property
    def has_args(self) -> bool:
        """Check if this group produces any bwrap args."""
        return bool(self.to_args())

    def get_item(self, name: str) -> UIField | None:
        """Get a UIField item by name."""
        for item in self.items:
            if item.name == name:
                return item
        return None

    def reset_to_defaults(self) -> None:
        """Reset all values to their defaults."""
        for item in self.items:
            self._values[item.name] = item.default
