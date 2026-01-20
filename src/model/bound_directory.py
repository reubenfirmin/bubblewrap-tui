"""Bound directory model."""

from dataclasses import dataclass
from pathlib import Path


@dataclass
class BoundDirectory:
    """A directory bound into the sandbox."""

    path: Path
    readonly: bool = True
    device: bool = False  # Use --dev-bind for device nodes

    def __str__(self) -> str:
        if self.device:
            return f"{self.path} (dev)"
        mode = "ro" if self.readonly else "rw"
        return f"{self.path} ({mode})"

    def to_args(self) -> list[str]:
        """Convert to bwrap arguments."""
        path_str = str(self.path)

        if self.device:
            return ["--dev-bind", path_str, path_str]

        flag = "--ro-bind" if self.readonly else "--bind"
        return [flag, path_str, path_str]
