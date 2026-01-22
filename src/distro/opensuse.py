"""openSUSE distribution configuration."""

from distro.base import DistroConfig
from distro.detector import register_distro


@register_distro
class OpenSUSEDistro(DistroConfig):
    """Configuration for openSUSE distributions."""

    name = "opensuse"
    aliases = ["opensuse-leap", "opensuse-tumbleweed", "sles"]
    package_manager = "zypper"

    def get_install_command(self, package: str) -> str:
        return f"sudo zypper install {package}"

    def get_ssl_cert_paths(self) -> list[str]:
        return [
            "/etc/ssl/certs",
            "/etc/pki/trust",
            "/var/lib/ca-certificates",
        ]
