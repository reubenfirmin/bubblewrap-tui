"""pasta installation detection and instructions."""

import shutil

from net.utils import detect_distro


def check_pasta() -> bool:
    """Check if pasta is installed."""
    return shutil.which("pasta") is not None


def get_install_instructions() -> str:
    """Return distro-specific install instructions for pasta (passt package)."""
    distro = detect_distro()

    instructions = {
        "fedora": "sudo dnf install passt",
        "rhel": "sudo dnf install passt",
        "centos": "sudo dnf install passt",
        "debian": "sudo apt install passt",
        "ubuntu": "sudo apt install passt",
        "arch": "sudo pacman -S passt",
        "manjaro": "sudo pacman -S passt",
        "opensuse": "sudo zypper install passt",
        "opensuse-leap": "sudo zypper install passt",
        "opensuse-tumbleweed": "sudo zypper install passt",
        "gentoo": "sudo emerge passt",
        "alpine": "sudo apk add passt",
        "void": "sudo xbps-install passt",
        "nixos": "nix-env -iA nixpkgs.passt",
    }

    if distro in instructions:
        return instructions[distro]

    # Fallback - check for package manager
    if shutil.which("apt"):
        return "sudo apt install passt"
    elif shutil.which("dnf"):
        return "sudo dnf install passt"
    elif shutil.which("pacman"):
        return "sudo pacman -S passt"
    elif shutil.which("zypper"):
        return "sudo zypper install passt"

    return "Install passt using your package manager"


def get_pasta_status() -> tuple[bool, str]:
    """Get pasta installation status and install command.

    Returns:
        Tuple of (is_installed, install_command_or_status_message).
    """
    if check_pasta():
        return (True, "pasta installed")
    else:
        return (False, get_install_instructions())
