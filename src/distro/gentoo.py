"""Gentoo Linux distribution configuration."""

from distro.base import DistroConfig
from distro.detector import register_distro


@register_distro
class GentooDistro(DistroConfig):
    """Configuration for Gentoo Linux."""

    name = "gentoo"
    aliases = ["calculate", "sabayon"]
    package_manager = "emerge"

    def get_install_command(self, package: str) -> str:
        return f"sudo emerge {package}"

    def get_ssl_cert_paths(self) -> list[str]:
        return [
            "/etc/ssl/certs",
            "/etc/ssl/cert.pem",
        ]
