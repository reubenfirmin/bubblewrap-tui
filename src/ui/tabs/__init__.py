"""Tab modules for the Bubblewrap TUI."""

from ui.tabs.directories import compose_directories_tab
from ui.tabs.environment import compose_environment_tab
from ui.tabs.filesystem import compose_filesystem_tab
from ui.tabs.overlays import compose_overlays_tab
from ui.tabs.profiles import compose_profiles_tab
from ui.tabs.sandbox import compose_sandbox_tab
from ui.tabs.summary import compose_summary_tab

__all__ = [
    "compose_directories_tab",
    "compose_environment_tab",
    "compose_filesystem_tab",
    "compose_overlays_tab",
    "compose_profiles_tab",
    "compose_sandbox_tab",
    "compose_summary_tab",
]
