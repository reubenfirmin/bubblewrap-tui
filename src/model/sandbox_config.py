"""Sandbox configuration model."""

from dataclasses import dataclass, field

from model.bound_directory import BoundDirectory
from model.desktop_config import DesktopConfig
from model.environment_config import EnvironmentConfig
from model.filesystem_config import FilesystemConfig
from model.namespace_config import NamespaceConfig
from model.network_config import NetworkConfig
from model.overlay_config import OverlayConfig
from model.process_config import ProcessConfig


@dataclass
class SandboxConfig:
    """Configuration for the sandbox."""

    command: list[str] = field(default_factory=list)
    bound_dirs: list[BoundDirectory] = field(default_factory=list)
    overlays: list[OverlayConfig] = field(default_factory=list)
    drop_caps: set[str] = field(default_factory=set)

    # Composed sub-configs
    environment: EnvironmentConfig = field(default_factory=EnvironmentConfig)
    filesystem: FilesystemConfig = field(default_factory=FilesystemConfig)
    network: NetworkConfig = field(default_factory=NetworkConfig)
    desktop: DesktopConfig = field(default_factory=DesktopConfig)
    namespace: NamespaceConfig = field(default_factory=NamespaceConfig)
    process: ProcessConfig = field(default_factory=ProcessConfig)

    def build_command(self) -> list[str]:
        """Build the complete bwrap command."""
        from bwrap import BubblewrapSerializer
        return BubblewrapSerializer(self).serialize()

    def get_explanation(self) -> str:
        """Generate a human-readable explanation of the sandbox."""
        from bwrap import BubblewrapSummarizer
        return BubblewrapSummarizer(self).summarize()
