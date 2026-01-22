"""Alpine Linux distribution configuration."""

from distro.base import DistroConfig
from distro.detector import register_distro


@register_distro
class AlpineDistro(DistroConfig):
    """Configuration for Alpine Linux."""

    name = "alpine"
    aliases = []
    package_manager = "apk"

    def get_install_command(self, package: str) -> str:
        return f"sudo apk add {package}"

    def get_ssl_cert_paths(self) -> list[str]:
        return [
            "/etc/ssl/certs",
            "/etc/ssl/cert.pem",
        ]

    def get_system_overlay_paths(self) -> list[str]:
        # Alpine uses musl and has a simpler filesystem layout
        return ["/usr", "/bin", "/lib", "/sbin"]
