"""pasta installation detection and instructions."""

import shutil


def check_pasta() -> bool:
    """Check if pasta is installed."""
    return shutil.which("pasta") is not None


def get_install_instructions() -> str:
    """Return distro-specific install instructions for pasta (passt package)."""
    from distro import get_current_distro

    distro = get_current_distro()
    return distro.get_install_command("passt")


def get_pasta_status() -> tuple[bool, str]:
    """Get pasta installation status and install command.

    Returns:
        Tuple of (is_installed, install_command_or_status_message).
    """
    if check_pasta():
        return (True, "pasta installed")
    else:
        return (False, get_install_instructions())
