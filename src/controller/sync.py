"""ConfigSyncManager: bidirectional UI ↔ Config synchronization."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable

from textual.containers import VerticalScroll
from textual.css.query import NoMatches
from textual.widgets import Button, Checkbox, Input

from constants import MAX_UID_GID
from ui.ids import css
import ui.ids as ids

if TYPE_CHECKING:
    from textual.app import App

    from model import SandboxConfig

log = logging.getLogger(__name__)


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
    # Filesystem options (Virtual Filesystems)
    FieldMapping(ids.OPT_PROC, "filesystem.mount_proc", Checkbox),
    FieldMapping(ids.OPT_TMP, "filesystem.mount_tmp", Checkbox),
    FieldMapping(ids.OPT_TMPFS_SIZE, "filesystem.tmpfs_size", Input, lambda v: v.strip()),

    # Quick Shortcuts (system paths + user config)
    # These sync checkbox state for profile saving/loading
    # The bound_dirs sync is handled separately in app.py
    FieldMapping(ids.OPT_USR, "filesystem.bind_usr", Checkbox),
    FieldMapping(ids.OPT_BIN, "filesystem.bind_bin", Checkbox),
    FieldMapping(ids.OPT_LIB, "filesystem.bind_lib", Checkbox),
    FieldMapping(ids.OPT_LIB64, "filesystem.bind_lib64", Checkbox),
    FieldMapping(ids.OPT_SBIN, "filesystem.bind_sbin", Checkbox),
    FieldMapping(ids.OPT_ETC, "filesystem.bind_etc", Checkbox),
    FieldMapping(ids.OPT_USER_CONFIG, "desktop.bind_user_config", Checkbox),

    # Network options
    FieldMapping(ids.OPT_NET, "network.share_net", Checkbox),
    FieldMapping(ids.OPT_RESOLV_CONF, "network.bind_resolv_conf", Checkbox),
    FieldMapping(ids.OPT_SSL_CERTS, "network.bind_ssl_certs", Checkbox),

    # Desktop integration
    FieldMapping(ids.OPT_DBUS, "desktop.allow_dbus", Checkbox),
    FieldMapping(ids.OPT_DISPLAY, "desktop.allow_display", Checkbox),
    # Note: bind_user_config is handled via Quick Shortcuts in directories tab

    # User identity (unshare_user, uid, gid, username, synthetic_passwd)
    FieldMapping(ids.OPT_UNSHARE_USER, "user.unshare_user", Checkbox),
    FieldMapping(ids.OPT_UID, "user.uid", Input, _validate_uid_gid),
    FieldMapping(ids.OPT_GID, "user.gid", Input, _validate_uid_gid),
    FieldMapping(ids.OPT_USERNAME, "user.username", Input, lambda v: v.strip()),
    FieldMapping(ids.OPT_SYNTHETIC_PASSWD, "user.synthetic_passwd", Checkbox),
    # Note: overlay_home is UI-only (like directory shortcuts) - not synced to model

    # Namespaces (PID, IPC, UTS, cgroup)
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
    """Manages bidirectional UI ↔ Config synchronization.

    This class handles the two-way binding between Textual UI widgets and the
    SandboxConfig model. It provides methods for:

    1. **UI → Config** (sync_config_from_ui): Read values from UI widgets and
       update the config model. Call this before saving a profile or executing.

    2. **Config → UI** (sync_ui_from_config): Read values from the config model
       and update UI widgets. Call this after loading a profile.

    3. **Inverse sync** (sync_shortcuts_from_bound_dirs): Derive UI state from
       data model. Used when bound_dirs is the source of truth (profile load).

    Widget caching is used to avoid repeated DOM queries. Call clear_cache()
    when widgets are remounted (e.g., after profile load triggers UI rebuild).

    Example usage:
        # After user edits UI, before saving:
        sync_manager.sync_config_from_ui()
        profile.save(config)

        # After loading a profile:
        sync_manager.clear_cache()
        sync_manager.sync_ui_from_config()
    """

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

    def sync_shortcuts_from_bound_dirs(self) -> None:
        """Derive shortcut checkbox states from existing bound_dirs.

        This is the inverse of the normal sync flow. When loading a profile,
        the bound_dirs list is the source of truth. This method sets the
        checkbox states to match which system paths are already bound.
        """
        from model.groups import QUICK_SHORTCUTS

        # Get resolved paths from bound_dirs
        bound_paths = {bd.path.resolve() for bd in self.config.bound_dirs}

        for field in QUICK_SHORTCUTS:
            shortcut_path = getattr(field, "shortcut_path", None)
            if shortcut_path is None:
                continue

            # Check if this shortcut's path is in bound_dirs
            enabled = shortcut_path.resolve() in bound_paths

            # Set the config value (checkbox will sync from this)
            if field.name in ("bind_usr", "bind_bin", "bind_lib", "bind_lib64", "bind_sbin", "bind_etc"):
                setattr(self.config.filesystem, field.name, enabled)
            elif field.name == "bind_user_config":
                setattr(self.config.desktop, field.name, enabled)

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
            if self.config.user.unshare_user:
                uid_gid.remove_class("hidden")
            else:
                uid_gid.add_class("hidden")
        except NoMatches:
            log.debug("uid-gid-options not found")

        # Show virtual user options when user namespace enabled
        # Show username field only when uid > 0 (non-root needs a username)
        try:
            username_opts = self.app.query_one(css(ids.USERNAME_OPTIONS))
            virtual_user_opts = self.app.query_one(css(ids.VIRTUAL_USER_OPTIONS))
            uid = self.config.user.uid
            if self.config.user.unshare_user:
                # Always show overlay options when masking user identity
                virtual_user_opts.remove_class("hidden")
                # Only show username field for non-root (uid > 0)
                if uid > 0:
                    username_opts.remove_class("hidden")
                else:
                    username_opts.add_class("hidden")
            else:
                username_opts.add_class("hidden")
                virtual_user_opts.add_class("hidden")
        except NoMatches:
            log.debug("username-options or virtual-user-options not found")

    def sync_overlay_home_from_overlays(self) -> None:
        """Derive overlay_home checkbox state from existing overlays.

        This is the inverse of the normal flow. When loading a profile,
        the overlays list is the source of truth. This method sets the
        checkbox to match whether there's a home overlay.
        """
        uid = self.config.user.uid
        username = self.config.user.username

        # Determine expected home path
        if uid == 0:
            home_path = "/root"
        elif username:
            home_path = f"/home/{username}"
        else:
            home_path = None

        # Check if there's an overlay for the home directory
        has_home_overlay = False
        if home_path:
            has_home_overlay = any(ov.dest == home_path for ov in self.config.overlays)

        # Set the checkbox directly (it's UI-only, not in FIELD_MAPPINGS)
        try:
            checkbox = self.get_widget(ids.OPT_OVERLAY_HOME, Checkbox)
            if checkbox:
                checkbox.value = has_home_overlay
        except NoMatches:
            log.debug("overlay-home checkbox not found")

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

    def rebuild_quick_shortcuts_bound_dirs(
        self,
        bound_dir_item_class: type,
        on_update: Callable[[], None],
        on_remove: Callable[[Any], None],
    ) -> None:
        """Rebuild quick shortcut bound dirs from config checkbox states.

        Args:
            bound_dir_item_class: The BoundDirItem widget class
            on_update: Callback for updates
            on_remove: Callback for removal
        """
        from model import BoundDirectory
        from model.groups import QUICK_SHORTCUTS

        try:
            dirs_list = self.app.query_one(css(ids.BOUND_DIRS_LIST), VerticalScroll)

            # Now add items for each enabled quick shortcut
            for field in QUICK_SHORTCUTS:
                # Get the checkbox state from config
                if field.name in ("bind_usr", "bind_bin", "bind_lib", "bind_lib64", "bind_sbin", "bind_etc"):
                    enabled = getattr(self.config.filesystem, field.name, False)
                elif field.name == "bind_user_config":
                    enabled = getattr(self.config.desktop, field.name, False)
                else:
                    continue

                path = getattr(field, "shortcut_path", None)
                if not enabled or path is None or not path.exists():
                    continue

                # Check if already in bound_dirs (avoid duplicates)
                resolved = path.resolve()
                if any(bd.path.resolve() == resolved for bd in self.config.bound_dirs):
                    continue

                # Add to config and mount widget (same as file picker)
                bound_dir = BoundDirectory(path=path, readonly=True)
                self.config.bound_dirs.append(bound_dir)
                dirs_list.mount(
                    bound_dir_item_class(
                        bound_dir,
                        on_update,
                        on_remove,
                    )
                )
        except NoMatches:
            log.debug("Bound dirs list not found for quick shortcuts sync")
