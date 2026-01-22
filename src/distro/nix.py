"""NixOS distribution configuration."""

from distro.base import DistroConfig
from distro.detector import register_distro


@register_distro
class NixOSDistro(DistroConfig):
    """Configuration for NixOS.

    NixOS has a unique filesystem layout with the Nix store.
    """

    name = "nixos"
    aliases = []
    package_manager = "nix"

    def get_install_command(self, package: str) -> str:
        return f"nix-env -iA nixpkgs.{package}"

    def get_ssl_cert_paths(self) -> list[str]:
        return [
            "/etc/ssl/certs",
            "/etc/ssl/cert.pem",
            "/nix/var/nix/profiles/default/etc/ssl/certs",
        ]

    def get_system_overlay_paths(self) -> list[str]:
        # NixOS requires the Nix store to be available
        return ["/nix", "/usr", "/bin", "/lib", "/lib64", "/sbin"]
