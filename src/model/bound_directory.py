"""Bound directory model."""

from dataclasses import dataclass
from pathlib import Path


@dataclass
class BoundDirectory:
    """A directory bound into the sandbox."""

    path: Path
    readonly: bool = True

    def __str__(self) -> str:
        mode = "ro" if self.readonly else "rw"
        return f"{self.path} ({mode})"

    def to_args(self) -> list[str]:
        """Convert to bwrap arguments."""
        flag = "--ro-bind" if self.readonly else "--bind"
        path_str = str(self.path)
        return [flag, path_str, path_str]
