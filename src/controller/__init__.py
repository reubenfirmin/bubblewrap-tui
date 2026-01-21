"""Controller layer: mediates between UI widgets and config model.

This package contains:
- sync: ConfigSyncManager for bidirectional UI ↔ Config sync
- Event handler mixins for different UI areas
"""

from controller.sync import ConfigSyncManager
from controller.directories import DirectoryEventsMixin
from controller.overlays import OverlayEventsMixin
from controller.environment import EnvironmentEventsMixin
from controller.execute import ExecuteEventsMixin
from controller.network import NetworkEventsMixin

__all__ = [
    # Sync
    "ConfigSyncManager",
    # Event mixins
    "DirectoryEventsMixin",
    "EnvironmentEventsMixin",
    "ExecuteEventsMixin",
    "NetworkEventsMixin",
    "OverlayEventsMixin",
]
