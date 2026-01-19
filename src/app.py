"""Main TUI application for bui."""

import logging
import os
import shlex
from pathlib import Path

from textual import on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
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
    compose_filesystem_tab,
    compose_overlays_tab,
    compose_sandbox_tab,
    compose_summary_tab,
    reflow_env_columns,
)
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
            # Auto-detect command executable and bind its directory
            self._auto_bind_command_dir(command)
            # All env vars kept by default
            self.config.environment.keep_env_vars = set(os.environ.keys())
            self._loaded_from_profile = False
        self._execute_command = False

    def _auto_bind_command_dir(self, command: list[str]) -> None:
        """Auto-detect and bind the directory containing the command executable."""
        resolved_path = resolve_command_executable(command)
        if not resolved_path:
            return

        # Build active system binds dict
        active_binds = {
            attr: getattr(self.config.filesystem, attr)
            for attr in self.config.filesystem.SYSTEM_PATHS
        }

        # Check if already covered
        if not is_path_covered(
            resolved_path,
            self.config.bound_dirs,
            self.config.filesystem.SYSTEM_PATHS,
            active_binds,
        ):
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

            with TabPane("File Systems", id="filesystems-tab"):
                yield from compose_filesystem_tab(self._on_dev_mode_change)

            with TabPane("Overlays", id="overlays-tab"):
                yield from compose_overlays_tab()

            with TabPane("Sandbox", id="sandbox-tab"):
                yield from compose_sandbox_tab()

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
            pass

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
            pass

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
        sync.rebuild_overlays_list(OverlayItem, self._update_preview, self._remove_overlay)
        sync.sync_env_button_state()
        self._reflow_env_columns()

    # =========================================================================
    # Event Handlers - Checkboxes and Inputs
    # =========================================================================

    @on(Checkbox.Changed)
    def on_checkbox_changed(self, event: Checkbox.Changed) -> None:
        """Handle checkbox changes."""
        # Auto-enable DNS and SSL certs when network is toggled on
        if event.checkbox.id == ids.OPT_NET and event.value:
            try:
                self.query_one(css(ids.OPT_RESOLV_CONF), Checkbox).value = True
                self.query_one(css(ids.OPT_SSL_CERTS), Checkbox).value = True
            except NoMatches:
                pass
        # Show/hide UID/GID options when user namespace is toggled
        if event.checkbox.id == ids.OPT_UNSHARE_USER:
            try:
                uid_gid = self.query_one(css(ids.UID_GID_OPTIONS))
                if event.value:
                    uid_gid.remove_class("hidden")
                else:
                    uid_gid.add_class("hidden")
            except NoMatches:
                pass
        self._sync_config_from_ui()
        self._update_preview()

    @on(Input.Changed)
    def on_input_changed(self, event: Input.Changed) -> None:
        """Handle input changes."""
        self._sync_config_from_ui()
        self._update_preview()

    def _on_dev_mode_change(self, mode: str) -> None:
        """Handle /dev mode change."""
        self.config.filesystem.dev_mode = mode
        self._update_preview()

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
            self.config.overlays.remove(item.overlay)
            item.remove()
            # Hide header when no overlays left
            if not self.config.overlays:
                try:
                    self.query_one(css(ids.OVERLAY_HEADER)).add_class("hidden")
                except NoMatches:
                    pass
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
