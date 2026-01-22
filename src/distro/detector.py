"""Distribution detection and registry."""

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from distro.base import DistroConfig

# Registry of all distribution configs
_distro_registry: dict[str, type["DistroConfig"]] = {}


def register_distro(cls: type["DistroConfig"]) -> type["DistroConfig"]:
    """Decorator to register a distribution config class.

    Registers the class under its primary name and all aliases.

    Args:
        cls: The DistroConfig subclass to register

    Returns:
        The same class (unchanged)
    """
    _distro_registry[cls.name] = cls
    for alias in cls.aliases:
        _distro_registry[alias] = cls
    return cls


def detect_distro_id() -> str | None:
    """Detect Linux distribution from /etc/os-release.

    Returns:
        Distribution ID (e.g., 'fedora', 'ubuntu', 'arch') or None if not detected.
    """
    os_release = Path("/etc/os-release")
    if not os_release.exists():
        return None

    try:
        content = os_release.read_text()
        for line in content.splitlines():
            if line.startswith("ID="):
                return line.split("=", 1)[1].strip().strip('"').lower()
    except OSError:
        pass
    return None


def get_distro_by_id(distro_id: str) -> "DistroConfig | None":
    """Get a distro config instance by ID.

    Args:
        distro_id: Distribution ID (e.g., "fedora", "ubuntu")

    Returns:
        DistroConfig instance or None if not found
    """
    cls = _distro_registry.get(distro_id.lower())
    if cls:
        return cls()
    return None


def get_current_distro() -> "DistroConfig":
    """Detect and return the current distribution's config.

    Returns:
        DistroConfig instance for current system, or GenericDistro as fallback.
    """
    from distro.generic import GenericDistro

    distro_id = detect_distro_id()
    if distro_id:
        distro = get_distro_by_id(distro_id)
        if distro:
            return distro

    return GenericDistro()


def list_supported_distros() -> list[str]:
    """Get list of supported distribution names.

    Returns:
        Sorted list of primary distribution names (not aliases)
    """
    seen = set()
    names = []
    for name, cls in _distro_registry.items():
        if cls.name not in seen:
            seen.add(cls.name)
            names.append(cls.name)
    return sorted(names)
