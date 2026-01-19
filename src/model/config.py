"""Config: a collection of ConfigGroups for a tab."""

from __future__ import annotations

from dataclasses import dataclass, field

from model.config_group import ConfigGroup


@dataclass
class Config:
    """A configuration containing multiple groups.

    Each Config typically maps to one UI tab.
    """

    name: str
    groups: list[ConfigGroup] = field(default_factory=list)

    def get_group(self, name: str) -> ConfigGroup | None:
        """Get a group by name."""
        for group in self.groups:
            if group.name == name:
                return group
        return None

    def to_args(self) -> list[str]:
        """Collect bwrap args from all groups."""
        args = []
        for group in self.groups:
            args.extend(group.to_args())
        return args
