"""Fedora and RHEL-based distribution configuration."""

from distro.base import DistroConfig
from distro.detector import register_distro


@register_distro
class FedoraDistro(DistroConfig):
    """Configuration for Fedora and RHEL-based distributions."""

    name = "fedora"
    aliases = ["rhel", "centos", "rocky", "almalinux", "ol"]  # Oracle Linux
    package_manager = "dnf"

    def get_install_command(self, package: str) -> str:
        return f"sudo dnf install {package}"

    def get_ssl_cert_paths(self) -> list[str]:
        return [
            "/etc/pki/tls/certs",
            "/etc/pki/ca-trust/extracted",
            "/etc/ssl/certs",
        ]
