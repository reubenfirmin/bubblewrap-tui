"""Generic fallback distribution configuration."""

import shutil

from distro.base import DistroConfig
from distro.detector import register_distro


@register_distro
class GenericDistro(DistroConfig):
    """Fallback configuration for unknown distributions.

    Attempts to detect the package manager at runtime.
    """

    name = "generic"
    aliases = []
    package_manager = "unknown"

    def get_install_command(self, package: str) -> str:
        """Detect package manager and return install command."""
        if shutil.which("apt"):
            return f"sudo apt install {package}"
        elif shutil.which("dnf"):
            return f"sudo dnf install {package}"
        elif shutil.which("pacman"):
            return f"sudo pacman -S {package}"
        elif shutil.which("zypper"):
            return f"sudo zypper install {package}"
        elif shutil.which("apk"):
            return f"sudo apk add {package}"
        elif shutil.which("emerge"):
            return f"sudo emerge {package}"
        elif shutil.which("xbps-install"):
            return f"sudo xbps-install {package}"
        elif shutil.which("nix-env"):
            return f"nix-env -iA nixpkgs.{package}"
        else:
            return f"Install {package} using your package manager"
