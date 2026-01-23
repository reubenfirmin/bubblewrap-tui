"""Virtual file management for sandbox injection.

This module consolidates the creation and management of virtual files
that are injected into the sandbox via --ro-bind, including:
- /etc/passwd and /etc/group for synthetic users
- /etc/resolv.conf for DNS proxy

All virtual files are written to a temp directory and bound read-only.
"""

from __future__ import annotations

import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from fileutils import write_file_atomic

if TYPE_CHECKING:
    from model.sandbox_config import SandboxConfig


@dataclass
class VirtualFile:
    """A virtual file to inject into the sandbox."""

    source_path: str  # Path on host (temp file)
    dest_path: str  # Path in sandbox
    description: str  # Human-readable description


@dataclass
class VirtualFileManager:
    """Manages virtual files for sandbox injection.

    Creates temp files and tracks what will be injected into the sandbox.
    """

    tmp_dir: str = field(default_factory=lambda: tempfile.mkdtemp(prefix="bui-vfiles-"))
    files: list[VirtualFile] = field(default_factory=list)

    def add_file(self, content: str, dest_path: str, description: str) -> str:
        """Add a virtual file to be injected.

        Args:
            content: File content
            dest_path: Destination path in sandbox (e.g., /etc/passwd)
            description: Human-readable description

        Returns:
            Path to the created temp file

        Raises:
            OSError: If file creation fails (temp dir is cleaned up)
        """
        # Create filename from dest_path (e.g., /etc/passwd -> passwd)
        filename = Path(dest_path).name
        file_path = Path(self.tmp_dir) / filename
        try:
            write_file_atomic(file_path, content, 0o444)  # Read-only
        except OSError:
            # Clean up temp directory on failure to avoid leaking
            shutil.rmtree(self.tmp_dir, ignore_errors=True)
            raise

        self.files.append(VirtualFile(
            source_path=str(file_path),
            dest_path=dest_path,
            description=description,
        ))

        return str(file_path)

    def get_file_map(self) -> dict[str, str]:
        """Get mapping of dest_path -> source_path for bwrap args."""
        return {vf.dest_path: vf.source_path for vf in self.files}

    def get_summary(self) -> list[str]:
        """Get human-readable summary of virtual files."""
        return [f"{vf.dest_path}: {vf.description}" for vf in self.files]

    def get_bwrap_args(self) -> list[str]:
        """Get bwrap args for all virtual files."""
        args = []
        for vf in self.files:
            args.extend(["--ro-bind", vf.source_path, vf.dest_path])
        return args


def create_virtual_files(config: "SandboxConfig") -> VirtualFileManager:
    """Create all virtual files needed for a sandbox config.

    This is the main entry point - call this to get a VirtualFileManager
    with all necessary files created.

    Args:
        config: The sandbox configuration

    Returns:
        VirtualFileManager with all files created
    """
    manager = VirtualFileManager()

    # Add synthetic passwd/group if enabled
    _add_user_files(manager, config)

    return manager


def _add_user_files(manager: VirtualFileManager, config: "SandboxConfig") -> None:
    """Add synthetic passwd/group files if enabled."""
    from bwrap import BubblewrapSerializer

    virtual_user_data = BubblewrapSerializer(config).get_virtual_user_data()

    for content, dest_path in virtual_user_data:
        if dest_path == "/etc/passwd":
            desc = "Synthetic user identity"
        elif dest_path == "/etc/group":
            desc = "Synthetic group"
        else:
            desc = "Virtual file"

        manager.add_file(content, dest_path, desc)
