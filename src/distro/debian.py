"""Debian and Ubuntu-based distribution configuration."""

from distro.base import DistroConfig
from distro.detector import register_distro


@register_distro
class DebianDistro(DistroConfig):
    """Configuration for Debian and Ubuntu-based distributions."""

    name = "debian"
    aliases = ["ubuntu", "linuxmint", "pop", "elementary", "zorin", "kali"]
    package_manager = "apt"

    def get_install_command(self, package: str) -> str:
        return f"sudo apt install {package}"

    def get_ssl_cert_paths(self) -> list[str]:
        return [
            "/etc/ssl/certs",
            "/usr/share/ca-certificates",
            "/usr/local/share/ca-certificates",
        ]
