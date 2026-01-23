"""Overlay filesystem configuration model."""

from dataclasses import dataclass
from pathlib import Path


@dataclass
class OverlayConfig:
    """An overlay filesystem configuration.

    Modes:
        tmpfs: Empty writable directory (no source needed)
        overlay: Writable layer on existing dir, changes in RAM
        persistent: Writable layer on existing dir, changes saved to disk
    """

    source: str  # Real directory to overlay (required for overlay/persistent modes)
    dest: str  # Mount point in sandbox
    mode: str = "tmpfs"  # "tmpfs", "overlay", or "persistent"
    write_dir: str = ""  # For persistent mode - where changes are stored
    work_dir: str = ""  # Explicit work dir (overrides auto-generated)

    def get_work_dir(self) -> str:
        """Get work directory, using explicit value if set, otherwise auto-generate."""
        if self.work_dir:
            return self.work_dir
        if self.write_dir:
            return str(Path(self.write_dir).parent / ".overlay-work")
        return ""

    def to_args(self) -> list[str]:
        """Convert to bwrap arguments."""
        if not self.dest:
            return []

        if self.mode == "tmpfs":
            # Empty writable directory (RAM storage)
            return ["--tmpfs", self.dest]
        elif self.mode == "overlay":
            # Writable layer on existing dir, changes in RAM
            if not self.source:
                return []  # overlay mode requires source
            return ["--overlay-src", self.source, "--tmp-overlay", self.dest]
        elif self.mode == "persistent":
            # Writable layer, changes saved to disk
            if not self.write_dir:
                return []  # persistent mode requires write_dir
            work_dir = self.get_work_dir()
            if self.source:
                # With source: overlay on existing dir
                return ["--overlay-src", self.source, "--overlay", self.write_dir, work_dir, self.dest]
            else:
                # Without source: bind write_dir directly (empty persistent home)
                return ["--bind", self.write_dir, self.dest]
        return []
