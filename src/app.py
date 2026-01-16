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
    OverlayConfig,
    SandboxConfig,
)
from profiles import ProfileManager
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
    ProfileItem,
    compose_directories_tab,
    compose_environment_tab,
    compose_filesystem_tab,
    compose_overlays_tab,
    compose_profiles_tab,
    compose_sandbox_tab,
    compose_summary_tab,
    reflow_env_columns,
)

# Set up logging to file
logging.basicConfig(
    filename="/tmp/bui.log",
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

        yield Container(
            Label(f"bui - {' '.join(self.config.command)}", id="header-title"),
            id="header-container",
        )

        with TabbedContent(id="main-content"):
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
                    self._format_command(),
                    self.config.get_explanation(),
                )

            with TabPane("Profiles", id="profiles-tab"):
                yield from compose_profiles_tab()

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
            status = self.query_one("#status-bar", Static)
            status.update(message)
        except NoMatches:
            pass

    def _format_command(self) -> str:
        """Format the command for display - compact single line."""
        args = self.config.build_command()
        return shlex.join(args)

    def _update_preview(self) -> None:
        """Update the command preview."""
        try:
            preview = self.query_one("#command-preview", Static)
            preview.update(self._format_command())
            explanation = self.query_one("#explanation", Static)
            explanation.update(self.config.get_explanation())
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
        if event.checkbox.id == "opt-net" and event.value:
            try:
                self.query_one("#opt-resolv-conf", Checkbox).value = True
                self.query_one("#opt-ssl-certs", Checkbox).value = True
            except NoMatches:
                pass
        # Show/hide UID/GID options when user namespace is toggled
        if event.checkbox.id == "opt-unshare-user":
            try:
                uid_gid = self.query_one("#uid-gid-options")
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
                    self.query_one("#overlay-header").add_class("hidden")
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

    def _set_config(self, config: SandboxConfig) -> None:
        """Set a new config (called by ProfileManager)."""
        self.config = config
        # Update sync manager reference to new config
        self._sync_manager = ConfigSyncManager(self, self.config)

    def _on_profile_loaded(self) -> None:
        """Called when a profile is loaded (sync UI)."""
        self._sync_ui_from_config()
        self._update_preview()

    @on(Button.Pressed, "#save-profile-btn")
    def on_save_profile_pressed(self, event: Button.Pressed) -> None:
        """Save the current config as a profile."""
        try:
            name_input = self.query_one("#profile-name-input", Input)
            name = name_input.value.strip()
            pm = self._get_profile_manager()
            pm.save_profile(name, self._sync_config_from_ui)
            pm.refresh_profiles_list(ProfileItem)
            name_input.value = ""
        except NoMatches:
            pass

    @on(Button.Pressed, "#load-profile-btn")
    def on_load_profile_from_path_pressed(self, event: Button.Pressed) -> None:
        """Load a profile from a specified path."""
        try:
            path_input = self.query_one("#load-profile-path", Input)
            path_str = path_input.value.strip()
            if not path_str:
                self._set_status("Enter a profile path")
                return
            path = Path(path_str).expanduser().resolve()
            if not path.exists():
                self._set_status(f"Profile not found: {path}")
                return
            self._get_profile_manager().load_profile(path)
            path_input.value = ""
        except NoMatches:
            pass

    # =========================================================================
    # Lifecycle
    # =========================================================================

    def on_mount(self) -> None:
        """Called when the app is mounted."""
        self._get_profile_manager().refresh_profiles_list(ProfileItem)
        # If loaded from profile, sync UI to show loaded config
        if self._loaded_from_profile:
            self._sync_ui_from_config()
