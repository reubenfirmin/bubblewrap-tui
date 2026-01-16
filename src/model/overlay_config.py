"""Overlay filesystem configuration model."""

from dataclasses import dataclass
from pathlib import Path


@dataclass
class OverlayConfig:
    """An overlay filesystem configuration."""

    source: str  # Real directory to overlay
    dest: str  # Mount point in sandbox
    mode: str = "tmpfs"  # "tmpfs" or "persistent"
    write_dir: str = ""  # For persistent mode - where changes are stored

    def get_work_dir(self) -> str:
        """Auto-generate work dir from write dir."""
        if self.write_dir:
            return str(Path(self.write_dir).parent / ".overlay-work")
        return ""

    def to_args(self) -> list[str]:
        """Convert to bwrap arguments."""
        if not self.source or not self.dest:
            return []
        args = ["--overlay-src", self.source]
        if self.mode == "tmpfs":
            args.extend(["--tmp-overlay", self.dest])
        elif self.mode == "persistent" and self.write_dir:
            work_dir = self.get_work_dir()
            args.extend(["--overlay", self.write_dir, work_dir, self.dest])
        return args
