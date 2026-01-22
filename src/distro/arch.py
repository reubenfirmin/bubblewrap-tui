"""Arch Linux and derivatives configuration."""

from distro.base import DistroConfig
from distro.detector import register_distro


@register_distro
class ArchDistro(DistroConfig):
    """Configuration for Arch Linux and derivatives."""

    name = "arch"
    aliases = ["manjaro", "endeavouros", "garuda", "artix"]
    package_manager = "pacman"

    def get_install_command(self, package: str) -> str:
        return f"sudo pacman -S {package}"

    def get_ssl_cert_paths(self) -> list[str]:
        return [
            "/etc/ssl/certs",
            "/etc/ca-certificates",
        ]
