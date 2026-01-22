"""Base class for distribution-specific configuration."""

from abc import ABC, abstractmethod
from typing import ClassVar


class DistroConfig(ABC):
    """Abstract base class for distribution-specific configuration.

    Subclasses implement distro-specific package management, path detection,
    and profile generation.
    """

    name: ClassVar[str]  # Primary distro identifier (e.g., "fedora")
    aliases: ClassVar[list[str]] = []  # Alternative IDs (e.g., ["rhel", "centos"])
    package_manager: ClassVar[str]  # Package manager name (e.g., "dnf")

    @abstractmethod
    def get_install_command(self, package: str) -> str:
        """Get the command to install a package.

        Args:
            package: Package name to install

        Returns:
            Full install command string (e.g., "sudo dnf install passt")
        """
        ...

    def get_ssl_cert_paths(self) -> list[str]:
        """Get SSL certificate paths for this distribution.

        Returns:
            List of paths to SSL certificate files/directories
        """
        # Default paths that work for most distributions
        return [
            "/etc/ssl/certs",
            "/etc/ssl/cert.pem",
            "/etc/pki/tls/certs",
            "/etc/pki/ca-trust/extracted",
        ]

    def get_dns_paths(self) -> list[str]:
        """Get DNS configuration paths for this distribution.

        Returns:
            List of paths to DNS configuration files
        """
        # Default paths that work for most distributions
        return [
            "/etc/resolv.conf",
            "/etc/nsswitch.conf",
        ]

    def get_system_overlay_paths(self) -> list[str]:
        """Get system paths that should be available as read-only binds.

        Returns:
            List of system paths to bind
        """
        # Standard paths for most distributions
        return ["/usr", "/bin", "/lib", "/lib64", "/sbin"]

    def generate_installable_profile(self) -> dict:
        """Generate an installable profile for this distribution.

        Returns:
            Profile dictionary suitable for JSON serialization
        """
        from pathlib import Path

        bound_dirs = []
        for path_str in self.get_system_overlay_paths():
            if Path(path_str).exists():
                bound_dirs.append({"path": path_str, "readonly": True})

        return {
            "bound_dirs": bound_dirs,
            "overlays": [
                {
                    "source": "",
                    "dest": "/home/sandbox",
                    "mode": "persistent",
                }
            ],
            "drop_caps": [],
            "_vfs_group": {
                "_values": {
                    "dev_mode": "minimal",
                    "mount_proc": True,
                    "mount_tmp": True,
                    "tmpfs_size": "",
                }
            },
            "_user_group": {
                "_values": {
                    "unshare_user": True,
                    "uid": 1000,
                    "gid": 1000,
                    "username": "sandbox",
                    "synthetic_passwd": True,
                }
            },
            "_isolation_group": {
                "_values": {
                    "unshare_pid": True,
                    "unshare_ipc": True,
                    "unshare_cgroup": True,
                    "disable_userns": False,
                    "seccomp_block_userns": True,
                }
            },
            "_hostname_group": {
                "_values": {
                    "unshare_uts": True,
                    "custom_hostname": "sandbox",
                }
            },
            "_process_group": {
                "_values": {
                    "die_with_parent": True,
                    "new_session": True,
                    "as_pid_1": False,
                    "chdir": "",
                }
            },
            "_network_group": {
                "_values": {
                    "share_net": True,
                    "bind_resolv_conf": True,
                    "bind_ssl_certs": True,
                }
            },
            "_desktop_group": {
                "_values": {
                    "allow_dbus": False,
                    "allow_display": False,
                    "bind_user_config": False,
                }
            },
            "_environment_group": {
                "_values": {
                    "clear_env": True,
                    "keep_env_vars": ["TERM"],
                    "unset_env_vars": [],
                    "custom_env_vars": {
                        "HOME": "/home/sandbox",
                        "PATH": "/usr/local/bin:/usr/bin:/bin:/usr/local/sbin:/usr/sbin:/sbin",
                    },
                }
            },
            "network_filter": {
                "mode": "filter",
                "hostname_filter": {"mode": "off", "hosts": []},
                "ip_filter": {
                    "mode": "blacklist",
                    "cidrs": [
                        "127.0.0.0/8",
                        "::1/128",
                        "10.0.0.0/8",
                        "172.16.0.0/12",
                        "192.168.0.0/16",
                        "169.254.0.0/16",
                        "fe80::/10",
                        "fc00::/7",
                    ],
                },
                "port_forwarding": {"expose_ports": [], "host_ports": []},
                "audit": {"pcap_path": None},
            },
        }
