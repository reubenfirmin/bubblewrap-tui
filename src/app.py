"""Main TUI application for bui."""

import logging
import os
import shlex
from pathlib import Path

from textual import on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal
from textual.css.query import NoMatches
from textual.reactive import reactive
from textual.widgets import (
    Button,
    Checkbox,
    Input,
    Label,
    Static,
    TabbedContent,
    TabPane,
)

from model import (
    BoundDirectory,
    FilterMode,
    OverlayConfig,
    SandboxConfig,
)
from profiles import Profile, ProfileManager, BUI_PROFILES_DIR
from controller import (
    ConfigSyncManager,
    DirectoryEventsMixin,
    EnvironmentEventsMixin,
    ExecuteEventsMixin,
    OverlayEventsMixin,
)
from detection import is_path_covered, resolve_command_executable
from ui import (
    BoundDirItem,
    DevModeCard,
    EnvVarItem,
    OverlayItem,
    compose_directories_tab,
    compose_environment_tab,
    compose_network_tab,
    compose_overlays_tab,
    compose_sandbox_tab,
    compose_summary_tab,
    reflow_env_columns,
)
from model.groups import QUICK_SHORTCUT_BY_CHECKBOX_ID, QUICK_SHORTCUTS
from ui.ids import css
from ui.modals import LoadProfileModal, SaveProfileModal
import ui.ids as ids

# Set up logging to XDG state directory
def _get_log_path() -> Path:
    """Get the log file path using XDG Base Directory spec."""
    xdg_state = os.environ.get("XDG_STATE_HOME", str(Path.home() / ".local" / "state"))
    log_dir = Path(xdg_state) / "bui"
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir / "bui.log"

logging.basicConfig(
    filename=str(_get_log_path()),
    level=logging.DEBUG,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
log = logging.getLogger(__name__)

# Load CSS from file (will be inlined by build.py)
APP_CSS = (Path(__file__).parent / "ui" / "styles.css").read_text()


class BubblewrapTUI(
    DirectoryEventsMixin,
    OverlayEventsMixin,
    EnvironmentEventsMixin,
    ExecuteEventsMixin,
    App,
):
    """TUI for configuring bubblewrap sandboxes."""

    TITLE = "Bubblewrap TUI"
    ENABLE_COMMAND_PALETTE = False
    CSS = APP_CSS  # Loaded from styles.css (inlined during build)

    BINDINGS = [
        Binding("enter", "execute", "Execute", show=True),
        Binding("escape", "cancel", "Cancel", show=True),
        Binding("a", "add_directory", "Add Dir", show=True),
    ]

    config: reactive[SandboxConfig] = reactive(SandboxConfig, recompose=False)

    def __init__(
        self, command: list[str], version: str = "0.0", config: SandboxConfig | None = None
    ) -> None:
        super().__init__()
        self.version = version
        self._sync_manager: ConfigSyncManager | None = None
        self._profile_manager: ProfileManager | None = None

        if config is not None:
            # Use provided config (from profile)
            self.config = config
            self._loaded_from_profile = True
        else:
            # Create new config
            self.config = SandboxConfig(command=command)
            # Bind current directory read-only by default
            cwd = Path.cwd().resolve()
            self.config.bound_dirs.append(BoundDirectory(path=cwd, readonly=True))
            # Initialize bound_dirs with default-checked quick shortcuts
            self._init_quick_shortcuts_bound_dirs()
            # Auto-detect command executable and bind its directory (after system paths added)
            self._auto_bind_command_dir(command)
            # All env vars kept by default
            self.config.environment.keep_env_vars = set(os.environ.keys())
            self._loaded_from_profile = False
        self._execute_command = False

    def _init_quick_shortcuts_bound_dirs(self) -> None:
        """Initialize bound_dirs with default-checked quick shortcuts."""
        for field in QUICK_SHORTCUTS:
            # Get the default value for this shortcut
            path = getattr(field, "shortcut_path", None)
            if path is None or not path.exists():
                continue

            # Check if this shortcut is enabled by default
            if field.name in ("bind_usr", "bind_bin", "bind_lib", "bind_lib64", "bind_sbin"):
                enabled = field.default  # True for these
            elif field.name in ("bind_etc", "bind_user_config"):
                enabled = False  # Never enabled by default
            else:
                enabled = field.default

            if not enabled:
                continue

            # Check if already in bound_dirs (avoid duplicates)
            resolved = path.resolve()
            if any(bd.path.resolve() == resolved for bd in self.config.bound_dirs):
                continue

            # Add to bound_dirs
            self.config.bound_dirs.append(BoundDirectory(path=path, readonly=True))

    def _auto_bind_command_dir(self, command: list[str]) -> None:
        """Auto-detect and bind the directory containing the command executable."""
        resolved_path = resolve_command_executable(command)
        if not resolved_path:
            return

        # Check if already covered by bound_dirs (includes system paths from quick shortcuts)
        if not is_path_covered(resolved_path, self.config.bound_dirs):
            self.config.bound_dirs.append(BoundDirectory(path=resolved_path.parent, readonly=True))

        # Update command to use resolved path
        self.config.command[0] = str(resolved_path)

    def compose(self) -> ComposeResult:
        log.info("compose() called")
        log.info(f"bound_dirs: {self.config.bound_dirs}")
        log.info(f"env vars count: {len(os.environ)}")

        yield Horizontal(
            Label(f"bui - {' '.join(self.config.command)}", id="header-title"),
            Button("Load", id="load-profile-btn", variant="default"),
            Button("Save", id="save-profile-btn", variant="default"),
            id="header-container",
        )

        with TabbedContent(id="config-tabs"):
            with TabPane("Directories", id="dirs-tab"):
                yield from compose_directories_tab(
                    self.config.bound_dirs,
                    self._update_preview,
                    self._remove_bound_dir,
                )

            with TabPane("Environment", id="env-tab"):
                yield from compose_environment_tab(self._toggle_env_var)

            with TabPane("Sandbox", id="sandbox-tab"):
                yield from compose_sandbox_tab(self._on_dev_mode_change)

            with TabPane("Network", id="network-tab"):
                yield from compose_network_tab(
                    self.config.network_filter,
                    self.config.network.share_net,
                    self.config.network.bind_resolv_conf,
                    self.config.network.bind_ssl_certs,
                    self._on_hostname_mode_change,
                    self._on_hostname_add,
                    self._on_hostname_remove,
                    self._on_ip_mode_change,
                    self._on_cidr_add,
                    self._on_cidr_remove,
                    self._on_port_add,
                    self._on_port_remove,
                )

            with TabPane("Overlays", id="overlays-tab"):
                yield from compose_overlays_tab()

            with TabPane("Summary", id="summary-tab"):
                yield from compose_summary_tab(
                    self.version,
                    self._format_command_colored(),
                    self._format_explanation_colored(),
                )

        yield Horizontal(
            Static("", id="status-bar"),
            Button("Execute [Enter]", id="execute-btn", variant="success"),
            Button("Cancel [Esc]", id="cancel-btn", variant="error"),
            id="footer-buttons",
        )

    # =========================================================================
    # Status and Preview
    # =========================================================================

    def _set_status(self, message: str) -> None:
        """Set status bar message."""
        try:
            status = self.query_one(css(ids.STATUS_BAR), Static)
            status.update(message)
        except NoMatches:
            log.debug("Status bar not found when setting: %s", message)

    def _format_command(self) -> str:
        """Format the command for display - compact single line."""
        args = self.config.build_command()
        return shlex.join(args)

    def _format_command_colored(self) -> str:
        """Format the command with section-based color coding."""
        from bwrap import BubblewrapSerializer
        return BubblewrapSerializer(self.config).serialize_colored()

    def _format_explanation_colored(self) -> str:
        """Format the explanation with section-based color coding."""
        from bwrap import BubblewrapSummarizer
        return BubblewrapSummarizer(self.config).summarize_colored()

    def _update_preview(self) -> None:
        """Update the command preview."""
        try:
            preview = self.query_one(css(ids.COMMAND_PREVIEW), Static)
            preview.update(self._format_command_colored())
            explanation = self.query_one(css(ids.EXPLANATION), Static)
            explanation.update(self._format_explanation_colored())
        except NoMatches:
            log.debug("Preview widgets not found during update")

    # =========================================================================
    # Config Sync (using ConfigSyncManager)
    # =========================================================================

    def _get_sync_manager(self) -> ConfigSyncManager:
        """Get or create the sync manager."""
        if self._sync_manager is None:
            self._sync_manager = ConfigSyncManager(self, self.config)
        return self._sync_manager

    def _sync_config_from_ui(self) -> None:
        """Sync the config from UI state using the sync manager."""
        self._get_sync_manager().sync_config_from_ui()

    def _sync_env_button_state(self) -> None:
        """Sync the clear/restore environment button state."""
        self._get_sync_manager().sync_env_button_state()

    def _sync_ui_from_config(self) -> None:
        """Sync the UI to reflect the current config state."""
        sync = self._get_sync_manager()
        sync.clear_cache()  # Clear cache as widgets may have been remounted
        sync.sync_ui_from_config()

        # Handle special cases via controller methods
        sync.sync_uid_gid_visibility()
        sync.sync_dev_mode(DevModeCard)
        sync.rebuild_bound_dirs_list(BoundDirItem, self._update_preview, self._remove_bound_dir)
        sync.rebuild_quick_shortcuts_bound_dirs(
            BoundDirItem, self._update_preview, self._remove_bound_dir
        )
        sync.rebuild_overlays_list(OverlayItem, self._update_preview, self._remove_overlay)
        sync.sync_overlay_home_from_overlays()
        self._update_home_overlay_label()
        sync.sync_env_button_state()
        self._reflow_env_columns()

    # =========================================================================
    # Event Handlers - Checkboxes and Inputs
    # =========================================================================

    @on(Checkbox.Changed)
    def on_checkbox_changed(self, event: Checkbox.Changed) -> None:
        """Handle checkbox changes."""
        # Handle network access toggle - show/hide full network options
        if event.checkbox.id == ids.OPT_NET:
            try:
                full_net_opts = self.query_one("#full-network-options", Container)
                if event.value:
                    full_net_opts.remove_class("hidden")
                    # Auto-enable DNS and SSL certs
                    self.query_one(css(ids.OPT_RESOLV_CONF), Checkbox).value = True
                    self.query_one(css(ids.OPT_SSL_CERTS), Checkbox).value = True
                else:
                    full_net_opts.add_class("hidden")
            except NoMatches:
                log.debug("Full network options container not found")
        # Show/hide UID/GID options when user namespace is toggled
        if event.checkbox.id == ids.OPT_UNSHARE_USER:
            try:
                uid_gid = self.query_one(css(ids.UID_GID_OPTIONS))
                if event.value:
                    uid_gid.remove_class("hidden")
                else:
                    uid_gid.add_class("hidden")
                # Sync username + virtual user options visibility
                try:
                    username_opts = self.query_one(css(ids.USERNAME_OPTIONS))
                    virtual_user_opts = self.query_one(css(ids.VIRTUAL_USER_OPTIONS))
                    uid = self.config.user.uid
                    if event.value:
                        # Always show overlay options when masking user
                        virtual_user_opts.remove_class("hidden")
                        self._update_home_overlay_label()
                        # Only show username for non-root
                        if uid > 0:
                            username_opts.remove_class("hidden")
                        else:
                            username_opts.add_class("hidden")
                    else:
                        username_opts.add_class("hidden")
                        virtual_user_opts.add_class("hidden")
                except NoMatches:
                    log.debug("Username/virtual user options container not found")
            except NoMatches:
                log.debug("UID/GID options container not found")
        # Handle quick shortcuts - sync with bound dirs list
        if event.checkbox.id in QUICK_SHORTCUT_BY_CHECKBOX_ID:
            field = QUICK_SHORTCUT_BY_CHECKBOX_ID[event.checkbox.id]
            self._handle_quick_shortcut_change(field, event.value)
        # Handle home overlay - sync with overlays list (synthetic_passwd doesn't need overlay)
        if event.checkbox.id == ids.OPT_OVERLAY_HOME:
            self._handle_overlay_home_change(event.value)
        # Handle network filtering enabled
        if event.checkbox.id == ids.NETWORK_ENABLED:
            self._on_network_enabled_change(event.value)
        self._sync_config_from_ui()
        self._update_preview()

    @on(Input.Changed)
    def on_input_changed(self, event: Input.Changed) -> None:
        """Handle input changes."""
        self._sync_config_from_ui()

        # Show/hide username field when UID changes (overlay options always visible when unshare_user)
        if event.input.id == ids.OPT_UID:
            try:
                username_opts = self.query_one(css(ids.USERNAME_OPTIONS))
                uid_str = event.value.strip()
                uid = int(uid_str) if uid_str.isdigit() else 0
                # Username field only for non-root (uid > 0)
                if self.config.user.unshare_user and uid > 0:
                    username_opts.remove_class("hidden")
                else:
                    username_opts.add_class("hidden")
                # Update home overlay label
                self._update_home_overlay_label()
            except (NoMatches, ValueError):
                log.debug("Username options container not found or invalid UID")

        # Update home overlay label when username changes
        if event.input.id == ids.OPT_USERNAME:
            self._update_home_overlay_label()

        self._update_preview()

    def _on_dev_mode_change(self, mode: str) -> None:
        """Handle /dev mode change."""
        self.config.filesystem.dev_mode = mode

    # =========================================================================
    # Network Filtering Callbacks
    # =========================================================================

    def _on_network_enabled_change(self, enabled: bool) -> None:
        """Handle network filtering enabled/disabled."""
        self.config.network_filter.enabled = enabled
        # Toggle visibility of filter options
        try:
            filter_opts = self.query_one("#filter-options", Container)
            filter_opts_right = self.query_one("#filter-options-right", Container)
            if enabled:
                filter_opts.remove_class("hidden")
                filter_opts_right.remove_class("hidden")
            else:
                filter_opts.add_class("hidden")
                filter_opts_right.add_class("hidden")
        except NoMatches:
            pass
        self._update_preview()

    def _on_hostname_mode_change(self, mode: str) -> None:
        """Handle hostname filter mode change."""
        self.config.network_filter.hostname_filter.mode = FilterMode(mode)
        self._update_preview()

    def _on_hostname_add(self, hostname: str) -> None:
        """Handle hostname added to filter list."""
        # Already added by widget, just update preview
        self._update_preview()

    def _on_hostname_remove(self, hostname: str) -> None:
        """Handle hostname removed from filter list."""
        # Already removed by widget, just update preview
        self._update_preview()

    def _on_ip_mode_change(self, mode: str) -> None:
        """Handle IP filter mode change."""
        self.config.network_filter.ip_filter.mode = FilterMode(mode)
        self._update_preview()

    def _on_cidr_add(self, cidr: str) -> None:
        """Handle CIDR added to filter list."""
        # Already added by widget, just update preview
        self._update_preview()

    def _on_cidr_remove(self, cidr: str) -> None:
        """Handle CIDR removed from filter list."""
        # Already removed by widget, just update preview
        self._update_preview()

    def _on_port_add(self, port: int) -> None:
        """Handle port added to localhost access list."""
        # Already added by widget, just update preview
        self._update_preview()

    def _on_port_remove(self, port: int) -> None:
        """Handle port removed from localhost access list."""
        # Already removed by widget, just update preview
        self._update_preview()

    def _update_home_overlay_label(self) -> None:
        """Update the home overlay checkbox label and explanation based on uid/username."""
        try:
            checkbox = self.query_one(css(ids.OPT_OVERLAY_HOME), Checkbox)
            explanation = self.query_one(f"#{ids.OPT_OVERLAY_HOME}-explanation", Static)
            uid = self.config.user.uid
            username = self.config.user.username
            if uid == 0:
                checkbox.label = "Overlay /root"
                explanation.update("Ephemeral /root directory")
            elif username:
                checkbox.label = f"Overlay /home/{username}"
                explanation.update(f"Ephemeral /home/{username} directory")
            else:
                checkbox.label = "Overlay /home/{user}"
                explanation.update("Ephemeral home directory")
        except NoMatches:
            pass

    def _handle_quick_shortcut_change(self, field, enabled: bool) -> None:
        """Handle quick shortcut checkbox toggle - sync with bound dirs list.

        Args:
            field: UIField with shortcut_path attribute
            enabled: Whether the shortcut is enabled
        """
        from textual.containers import VerticalScroll

        path = getattr(field, "shortcut_path", None)
        if path is None or not path.exists():
            return

        try:
            dirs_list = self.query_one(css(ids.BOUND_DIRS_LIST), VerticalScroll)
            resolved = path.resolve()

            if enabled:
                # Check if already in bound_dirs (avoid duplicates)
                if any(bd.path.resolve() == resolved for bd in self.config.bound_dirs):
                    return

                # Add to config and mount widget (same as file picker)
                bound_dir = BoundDirectory(path=path, readonly=True)
                self.config.bound_dirs.append(bound_dir)
                dirs_list.mount(
                    BoundDirItem(
                        bound_dir,
                        self._update_preview,
                        self._remove_bound_dir,
                    )
                )
            else:
                # Remove from config and unmount widget
                for bd in list(self.config.bound_dirs):
                    if bd.path.resolve() == resolved:
                        self.config.bound_dirs.remove(bd)
                        # Find and remove the widget
                        for item in dirs_list.query(BoundDirItem):
                            if item.bound_dir is bd:
                                item.remove()
                                break
                        break
        except NoMatches:
            log.debug("Bound dirs list not found for quick shortcut sync")

    def _handle_overlay_home_change(self, enabled: bool) -> None:
        """Handle overlay home checkbox toggle - sync with overlays list.

        When enabled, creates an empty overlay for the user's home directory.
        - uid=0: /root
        - uid>0: /home/{username}
        Also sets HOME environment variable.
        """
        from textual.containers import VerticalScroll

        uid = self.config.user.uid
        username = self.config.user.username

        # Determine home path based on uid
        if uid == 0:
            dest = "/root"
        elif username:
            dest = f"/home/{username}"
        else:
            return  # uid > 0 but no username yet

        try:
            overlays_list = self.query_one(css(ids.OVERLAYS_LIST), VerticalScroll)

            if enabled:
                # Check if already exists
                if any(ov.dest == dest for ov in self.config.overlays):
                    return

                # Create overlay - source="" (empty, fresh home), mode=tmpfs
                overlay = OverlayConfig(source="", dest=dest, mode="tmpfs")
                self.config.overlays.append(overlay)
                overlays_list.mount(OverlayItem(overlay, self._update_preview, self._remove_overlay))
                # Show header if hidden
                try:
                    self.query_one(css(ids.OVERLAY_HEADER)).remove_class("hidden")
                except NoMatches:
                    pass
                # Set HOME environment variable
                self.config.environment.custom_env_vars["HOME"] = dest
            else:
                # Remove overlay for either /root or /home/{username}
                for ov in list(self.config.overlays):
                    if ov.dest == dest or (ov.dest.startswith("/home/") and not ov.source):
                        self.config.overlays.remove(ov)
                        for item in overlays_list.query(OverlayItem):
                            if item.overlay is ov:
                                item.remove()
                                break
                        break
                # Remove HOME if it matches
                home_val = self.config.environment.custom_env_vars.get("HOME")
                if home_val == dest or (home_val and home_val.startswith("/home/")):
                    del self.config.environment.custom_env_vars["HOME"]
                # Hide header if no overlays left
                if not self.config.overlays:
                    try:
                        self.query_one(css(ids.OVERLAY_HEADER)).add_class("hidden")
                    except NoMatches:
                        pass
        except NoMatches:
            log.debug("Overlays list not found for home overlay sync")

    # =========================================================================
    # Callbacks for Event Mixins
    # =========================================================================

    def _remove_bound_dir(self, item: BoundDirItem) -> None:
        """Remove a bound directory from the list."""
        if item.bound_dir in self.config.bound_dirs:
            self.config.bound_dirs.remove(item.bound_dir)
            item.remove()
            self._update_preview()
            self._set_status(f"Removed: {item.bound_dir.path}")

    def _remove_overlay(self, item: OverlayItem) -> None:
        """Remove an overlay from the list."""
        if item.overlay in self.config.overlays:
            overlay = item.overlay
            self.config.overlays.remove(overlay)
            item.remove()

            # Bi-directional sync: uncheck User card checkbox if this was a managed home overlay
            if overlay.dest.startswith("/home/") and not overlay.source:
                # Home overlay: /home/{username} with empty source
                try:
                    checkbox = self.query_one(css(ids.OPT_OVERLAY_HOME), Checkbox)
                    checkbox.value = False
                    self.config.user._group.set("overlay_home", False)
                    # Remove HOME env var if it matched this path
                    if self.config.environment.custom_env_vars.get("HOME") == overlay.dest:
                        del self.config.environment.custom_env_vars["HOME"]
                except NoMatches:
                    pass

            # Hide header when no overlays left
            if not self.config.overlays:
                try:
                    self.query_one(css(ids.OVERLAY_HEADER)).add_class("hidden")
                except NoMatches:
                    log.debug("Overlay header not found when hiding")
            self._update_preview()
            self._set_status("Overlay removed")

    def _toggle_env_var(self, name: str, keep: bool) -> None:
        """Toggle whether to keep an environment variable."""
        is_custom = name in self.config.environment.custom_env_vars
        if keep:
            self.config.environment.keep_env_vars.add(name)
            self.config.environment.unset_env_vars.discard(name)
        else:
            self.config.environment.keep_env_vars.discard(name)
            if is_custom:
                # Remove custom var entirely instead of unsetting
                del self.config.environment.custom_env_vars[name]
            else:
                self.config.environment.unset_env_vars.add(name)
        self._update_preview()

    def _reflow_env_columns(self) -> None:
        """Reflow environment variable items across columns."""
        reflow_env_columns(self, self.config.environment, EnvVarItem, self._toggle_env_var)

    # =========================================================================
    # Profile Management (using ProfileManager)
    # =========================================================================

    def _get_profile_manager(self) -> ProfileManager:
        """Get or create the profile manager."""
        if self._profile_manager is None:
            self._profile_manager = ProfileManager(
                app=self,
                get_config=lambda: self.config,
                set_config=self._set_config,
                on_status=self._set_status,
                on_config_loaded=self._on_profile_loaded,
            )
        return self._profile_manager

    @on(Button.Pressed, "#load-profile-btn")
    def on_load_profile_pressed(self, event: Button.Pressed) -> None:
        """Open load profile modal."""
        self.push_screen(LoadProfileModal(), self._on_profile_modal_result)

    @on(Button.Pressed, "#save-profile-btn")
    def on_save_profile_pressed(self, event: Button.Pressed) -> None:
        """Open save profile modal."""
        self.push_screen(SaveProfileModal(), self._on_save_profile_result)

    def _on_profile_modal_result(self, profile_path: Path | None) -> None:
        """Handle result from load profile modal."""
        if profile_path:
            self._get_profile_manager().load_profile(profile_path)

    def _on_save_profile_result(self, name: str | None) -> None:
        """Handle result from save profile modal."""
        if name:
            pm = self._get_profile_manager()
            pm.save_profile(name, self._sync_config_from_ui)
            self._set_status(f"Saved profile: {name}")

    def _set_config(self, config: SandboxConfig) -> None:
        """Set a new config (called by ProfileManager)."""
        self.config = config
        # Update sync manager reference to new config
        self._sync_manager = ConfigSyncManager(self, self.config)

    def _on_profile_loaded(self) -> None:
        """Called when a profile is loaded (sync UI)."""
        # First, derive checkbox states from bound_dirs (inverse sync)
        # This ensures Quick Shortcuts checkboxes reflect what's in the profile's bound_dirs
        self._get_sync_manager().sync_shortcuts_from_bound_dirs()
        self._sync_ui_from_config()
        self._update_preview()

    # =========================================================================
    # Mixin Handler Forwarding
    # =========================================================================
    # Textual's @on decorator only registers handlers defined on the class itself,
    # not on mixins. These forwarding handlers ensure events are routed to mixins.

    # Directory handlers (from DirectoryEventsMixin)
    @on(Button.Pressed, css(ids.ADD_DIR_BTN))
    def _on_add_dir_btn(self, event: Button.Pressed) -> None:
        """Forward to mixin handler."""
        self.on_add_dir_pressed(event)

    @on(Button.Pressed, css(ids.PARENT_DIR_BTN))
    def _on_parent_dir_btn(self, event: Button.Pressed) -> None:
        """Forward to mixin handler."""
        self.on_parent_dir_pressed(event)

    @on(Button.Pressed, css(ids.ADD_PATH_BTN))
    def _on_add_path_btn(self, event: Button.Pressed) -> None:
        """Forward to mixin handler."""
        self.on_add_path_pressed(event)

    @on(Input.Submitted, css(ids.PATH_INPUT))
    def _on_path_input_submit(self, event: Input.Submitted) -> None:
        """Forward to mixin handler."""
        self.on_path_input_submitted(event)

    # Environment handlers (from EnvironmentEventsMixin)
    @on(Button.Pressed, css(ids.TOGGLE_CLEAR_BTN))
    def _on_toggle_clear_btn(self, event: Button.Pressed) -> None:
        """Forward to mixin handler."""
        self.on_toggle_clear_pressed(event)

    @on(Button.Pressed, css(ids.ADD_ENV_BTN))
    def _on_add_env_btn(self, event: Button.Pressed) -> None:
        """Forward to mixin handler."""
        self.on_add_env_pressed(event)

    # Overlay handlers (from OverlayEventsMixin)
    @on(Button.Pressed, css(ids.ADD_OVERLAY_BTN))
    def _on_add_overlay_btn(self, event: Button.Pressed) -> None:
        """Forward to mixin handler."""
        self.on_add_overlay_pressed(event)

    # Execute handlers (from ExecuteEventsMixin)
    @on(Button.Pressed, css(ids.EXECUTE_BTN))
    def _on_execute_btn(self, event: Button.Pressed) -> None:
        """Forward to mixin handler."""
        self.on_execute_pressed(event)

    @on(Button.Pressed, css(ids.CANCEL_BTN))
    def _on_cancel_btn(self, event: Button.Pressed) -> None:
        """Forward to mixin handler."""
        self.on_cancel_pressed(event)

    # =========================================================================
    # Lifecycle
    # =========================================================================

    def on_mount(self) -> None:
        """Called when the app is mounted."""
        self._mounted = True  # Track that initial mount is complete
        # If loaded from profile, sync UI to show loaded config
        if self._loaded_from_profile:
            self._sync_ui_from_config()
        # Focus the tab bar for keyboard navigation
        from textual.widgets import Tabs
        self.query_one("#config-tabs").query_one(Tabs).focus()
