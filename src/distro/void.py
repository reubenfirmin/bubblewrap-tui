"""Void Linux distribution configuration."""

from distro.base import DistroConfig
from distro.detector import register_distro


@register_distro
class VoidDistro(DistroConfig):
    """Configuration for Void Linux."""

    name = "void"
    aliases = []
    package_manager = "xbps"

    def get_install_command(self, package: str) -> str:
        return f"sudo xbps-install {package}"

    def get_ssl_cert_paths(self) -> list[str]:
        return [
            "/etc/ssl/certs",
            "/etc/ssl/cert.pem",
        ]
