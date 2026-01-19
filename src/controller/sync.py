"""ConfigSyncManager: bidirectional UI ↔ Config synchronization."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable

from textual.containers import VerticalScroll
from textual.css.query import NoMatches
from textual.widgets import Button, Checkbox, Input

from ui.ids import css
import ui.ids as ids

if TYPE_CHECKING:
    from textual.app import App

    from model import SandboxConfig

log = logging.getLogger(__name__)

# Valid range for Unix UID/GID values
MAX_UID_GID = 65535


def _validate_uid_gid(value: str) -> int | None:
    """Validate UID/GID is numeric and in valid range (0-65535)."""
    stripped = value.strip()
    if not stripped.isdigit():
        return None
    num = int(stripped)
    return num if 0 <= num <= MAX_UID_GID else None


@dataclass
class FieldMapping:
    """Maps a UI widget to a config field."""

    widget_id: str
    config_path: str  # e.g., "filesystem.mount_proc"
    widget_type: type  # Checkbox or Input
    value_transform: Callable[[Any], Any] | None = None  # Transform UI value to config value
    inverse_transform: Callable[[Any], Any] | None = None  # Transform config value to UI value


# Registry of all checkbox/input mappings
# These map widget IDs to config paths for automatic sync
FIELD_MAPPINGS: list[FieldMapping] = [
    # Filesystem options
    FieldMapping(ids.OPT_PROC, "filesystem.mount_proc", Checkbox),
    FieldMapping(ids.OPT_TMP, "filesystem.mount_tmp", Checkbox),
    FieldMapping(ids.OPT_TMPFS_SIZE, "filesystem.tmpfs_size", Input, lambda v: v.strip()),
    FieldMapping(ids.OPT_USR, "filesystem.bind_usr", Checkbox),
    FieldMapping(ids.OPT_BIN, "filesystem.bind_bin", Checkbox),
    FieldMapping(ids.OPT_LIB, "filesystem.bind_lib", Checkbox),
    FieldMapping(ids.OPT_LIB64, "filesystem.bind_lib64", Checkbox),
    FieldMapping(ids.OPT_SBIN, "filesystem.bind_sbin", Checkbox),
    FieldMapping(ids.OPT_ETC, "filesystem.bind_etc", Checkbox),

    # Network options
    FieldMapping(ids.OPT_NET, "network.share_net", Checkbox),
    FieldMapping(ids.OPT_RESOLV_CONF, "network.bind_resolv_conf", Checkbox),
    FieldMapping(ids.OPT_SSL_CERTS, "network.bind_ssl_certs", Checkbox),

    # Desktop integration
    FieldMapping(ids.OPT_DBUS, "desktop.allow_dbus", Checkbox),
    FieldMapping(ids.OPT_DISPLAY, "desktop.allow_display", Checkbox),
    FieldMapping(ids.OPT_USER_CONFIG, "desktop.bind_user_config", Checkbox),

    # Namespaces
    FieldMapping(ids.OPT_UNSHARE_USER, "namespace.unshare_user", Checkbox),
    FieldMapping(ids.OPT_UNSHARE_PID, "namespace.unshare_pid", Checkbox),
    FieldMapping(ids.OPT_UNSHARE_IPC, "namespace.unshare_ipc", Checkbox),
    FieldMapping(ids.OPT_UNSHARE_UTS, "namespace.unshare_uts", Checkbox),
    FieldMapping(ids.OPT_UNSHARE_CGROUP, "namespace.unshare_cgroup", Checkbox),
    FieldMapping(ids.OPT_DISABLE_USERNS, "namespace.disable_userns", Checkbox),

    # Process options
    FieldMapping(ids.OPT_DIE_WITH_PARENT, "process.die_with_parent", Checkbox),
    FieldMapping(ids.OPT_NEW_SESSION, "process.new_session", Checkbox),
    FieldMapping(ids.OPT_AS_PID_1, "process.as_pid_1", Checkbox),
    FieldMapping(ids.OPT_CHDIR, "process.chdir", Input),
    FieldMapping(ids.OPT_HOSTNAME, "environment.custom_hostname", Input),

    # UID/GID (int conversion with range validation 0-65535)
    FieldMapping(ids.OPT_UID, "process.uid", Input, _validate_uid_gid),
    FieldMapping(ids.OPT_GID, "process.gid", Input, _validate_uid_gid),
]


def _get_nested_attr(obj: Any, path: str) -> Any:
    """Get nested attribute like 'filesystem.mount_proc'."""
    for part in path.split('.'):
        obj = getattr(obj, part)
    return obj


def _set_nested_attr(obj: Any, path: str, value: Any) -> None:
    """Set nested attribute like 'filesystem.mount_proc'."""
    parts = path.split('.')
    for part in parts[:-1]:
        obj = getattr(obj, part)
    setattr(obj, parts[-1], value)


class ConfigSyncManager:
    """Manages bidirectional UI ↔ Config synchronization."""

    def __init__(self, app: App, config: Any) -> None:
        self.app = app
        self.config = config
        self._widget_cache: dict[str, Checkbox | Input] = {}

    def cache_widget(self, widget_id: str, widget: Checkbox | Input) -> None:
        """Cache a widget reference for fast lookup."""
        self._widget_cache[widget_id] = widget

    def get_widget(self, widget_id: str, widget_type: type) -> Checkbox | Input | None:
        """Get a widget by ID, using cache if available."""
        if widget_id in self._widget_cache:
            return self._widget_cache[widget_id]
        try:
            widget = self.app.query_one(f"#{widget_id}", widget_type)
            self._widget_cache[widget_id] = widget
            return widget
        except NoMatches:
            return None

    def sync_config_from_ui(self) -> None:
        """Read all UI widgets and update config."""
        for mapping in FIELD_MAPPINGS:
            widget = self.get_widget(mapping.widget_id, mapping.widget_type)
            if widget is None:
                continue

            try:
                if mapping.widget_type == Checkbox:
                    value = widget.value
                else:  # Input
                    value = widget.value
                    if mapping.value_transform:
                        transformed = mapping.value_transform(value)
                        if transformed is None:
                            continue  # Skip invalid values
                        value = transformed

                _set_nested_attr(self.config, mapping.config_path, value)
            except (ValueError, AttributeError) as e:
                log.debug(f"Error syncing {mapping.widget_id}: {e}")

    def sync_ui_from_config(self) -> None:
        """Read config and update all UI widgets."""
        for mapping in FIELD_MAPPINGS:
            widget = self.get_widget(mapping.widget_id, mapping.widget_type)
            if widget is None:
                continue

            try:
                value = _get_nested_attr(self.config, mapping.config_path)

                if mapping.inverse_transform:
                    value = mapping.inverse_transform(value)

                if mapping.widget_type == Checkbox:
                    widget.value = bool(value)
                else:  # Input
                    widget.value = str(value) if value is not None else ""
            except (ValueError, AttributeError) as e:
                log.debug(f"Error syncing UI {mapping.widget_id}: {e}")

    def clear_cache(self) -> None:
        """Clear the widget cache (call when widgets are remounted)."""
        self._widget_cache.clear()

    def rebuild_bound_dirs_list(
        self,
        bound_dir_item_class: type,
        on_update: Callable[[], None],
        on_remove: Callable[[Any], None],
    ) -> None:
        """Rebuild the bound directories list from config.

        Args:
            bound_dir_item_class: The BoundDirItem widget class
            on_update: Callback for updates
            on_remove: Callback for removal
        """
        try:
            dirs_list = self.app.query_one(css(ids.BOUND_DIRS_LIST), VerticalScroll)
            for item in list(dirs_list.query(bound_dir_item_class)):
                item.remove()
            for bd in self.config.bound_dirs:
                dirs_list.mount(bound_dir_item_class(bd, on_update, on_remove))
        except NoMatches:
            log.debug("bound-dirs-list not found")

    def rebuild_overlays_list(
        self,
        overlay_item_class: type,
        on_update: Callable[[], None],
        on_remove: Callable[[Any], None],
    ) -> None:
        """Rebuild the overlays list from config.

        Args:
            overlay_item_class: The OverlayItem widget class
            on_update: Callback for updates
            on_remove: Callback for removal
        """
        try:
            overlays_list = self.app.query_one(css(ids.OVERLAYS_LIST), VerticalScroll)
            for item in list(overlays_list.query(overlay_item_class)):
                item.remove()
            for ov in self.config.overlays:
                overlays_list.mount(overlay_item_class(ov, on_update, on_remove))
            # Show/hide overlay header
            header = self.app.query_one(css(ids.OVERLAY_HEADER))
            if self.config.overlays:
                header.remove_class("hidden")
            else:
                header.add_class("hidden")
        except NoMatches:
            log.debug("overlays-list not found")

    def sync_env_button_state(self) -> None:
        """Sync the clear/restore environment button state from config."""
        try:
            btn = self.app.query_one(css(ids.TOGGLE_CLEAR_BTN), Button)
            grid = self.app.query_one(css(ids.ENV_GRID_SCROLL))
            if self.config.environment.clear_env:
                grid.add_class("hidden")
                btn.label = "Restore System Env"
                btn.variant = "primary"
            else:
                grid.remove_class("hidden")
                btn.label = "Clear Sandbox Env"
                btn.variant = "error"
        except NoMatches:
            log.debug("env button/grid not found")

    def sync_uid_gid_visibility(self) -> None:
        """Show/hide UID/GID options based on user namespace setting."""
        try:
            uid_gid = self.app.query_one(css(ids.UID_GID_OPTIONS))
            if self.config.namespace.unshare_user:
                uid_gid.remove_class("hidden")
            else:
                uid_gid.add_class("hidden")
        except NoMatches:
            log.debug("uid-gid-options not found")

    def sync_dev_mode(self, dev_mode_card_class: type) -> None:
        """Sync the /dev mode card from config.

        Args:
            dev_mode_card_class: The DevModeCard widget class
        """
        try:
            dev_card = self.app.query_one(dev_mode_card_class)
            dev_card.set_mode(self.config.filesystem.dev_mode)
        except NoMatches:
            log.debug("DevModeCard not found")
