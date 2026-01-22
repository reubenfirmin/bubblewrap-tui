"""Distribution-specific configuration module.

This module provides distro-aware package management, path detection,
and installable profile generation.

Usage:
    from distro import get_current_distro, detect_distro_id

    # Get current system's distro configuration
    distro = get_current_distro()
    print(f"Detected: {distro.name}")
    print(f"Install passt: {distro.get_install_command('passt')}")

    # Generate a profile for this distro
    profile = distro.generate_installable_profile()
"""

# Import distro modules to trigger registration
from distro import (  # noqa: F401
    alpine,
    arch,
    debian,
    fedora,
    generic,
    gentoo,
    nix,
    opensuse,
    void,
)
from distro.base import DistroConfig
from distro.detector import (
    detect_distro_id,
    get_current_distro,
    get_distro_by_id,
    list_supported_distros,
)

__all__ = [
    "DistroConfig",
    "detect_distro_id",
    "get_current_distro",
    "get_distro_by_id",
    "list_supported_distros",
]
