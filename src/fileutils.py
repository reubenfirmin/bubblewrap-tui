"""File utilities for secure file operations."""

from __future__ import annotations

import os
from pathlib import Path


def write_file_atomic(path: Path, content: str, mode: int) -> None:
    """Write file with permissions set atomically to prevent TOCTOU races.

    Uses os.open() with O_CREAT | O_EXCL to atomically create the file
    with the correct permissions, avoiding a race window between write and chmod.

    Args:
        path: Path to write to
        content: File content
        mode: File permission mode (e.g., 0o755, 0o444)

    Raises:
        FileExistsError: If the file already exists
        OSError: If file creation fails
    """
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    try:
        os.write(fd, content.encode())
    finally:
        os.close(fd)
