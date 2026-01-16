"""Main TUI application for bui."""

import logging
import os
import shlex
import shutil
from pathlib import Path

from textual import on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
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

from config import BoundDirectory, OverlayConfig, SandboxConfig
from detection import detect_dbus_session, detect_display_server
from widgets import (
    AddEnvDialog,
    BoundDirItem,
    DevModeCard,
    EnvVarItem,
    FilteredDirectoryTree,
    OptionCard,
    OverlayItem,
)

# Set up logging to file
logging.basicConfig(
    filename="/tmp/bui.log",
    level=logging.DEBUG,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
log = logging.getLogger(__name__)

# Load CSS from file (will be inlined by build.py)
APP_CSS = (Path(__file__).parent / "styles.css").read_text()


class BubblewrapTUI(App):
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

    def __init__(self, command: list[str], version: str = "0.0") -> None:
        super().__init__()
        self.version = version
        self.config = SandboxConfig(command=command)
        # Bind current directory read-only by default
        cwd = Path.cwd().resolve()
        self.config.bound_dirs.append(BoundDirectory(path=cwd, readonly=True))
        # Auto-detect command executable and bind its directory
        self._auto_bind_command_dir(command)
        # All env vars kept by default
        self.config.keep_env_vars = set(os.environ.keys())
        self._execute_command = False

    def _auto_bind_command_dir(self, command: list[str]) -> None:
        """Auto-detect and bind the directory containing the command executable."""
        if not command:
            return
        cmd = command[0]
        # Try to resolve the command to an absolute path
        resolved = None
        if os.path.isabs(cmd):
            # Absolute path provided
            if os.path.isfile(cmd) and os.access(cmd, os.X_OK):
                resolved = cmd
        else:
            # Search PATH using shutil.which
            resolved = shutil.which(cmd)

        if resolved:
            resolved_path = Path(resolved).resolve()
            cmd_dir = resolved_path.parent
            # Check if already bound (or parent is bound)
            already_bound = False
            for bd in self.config.bound_dirs:
                try:
                    resolved_path.relative_to(bd.path)
                    already_bound = True
                    break
                except ValueError:
                    pass
            # Also check system paths
            for attr, sys_path in self.config.SYSTEM_PATHS.items():
                if getattr(self.config, attr):
                    try:
                        resolved_path.relative_to(sys_path)
                        already_bound = True
                        break
                    except ValueError:
                        pass
            if not already_bound:
                self.config.bound_dirs.append(BoundDirectory(path=cmd_dir, readonly=True))
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

        # Build directory items
        dir_items = []
        for bd in self.config.bound_dirs:
            log.info(f"Creating BoundDirItem for {bd.path}")
            dir_items.append(BoundDirItem(bd, self._update_preview, self._remove_bound_dir))
        log.info(f"Created {len(dir_items)} dir items")

        with TabbedContent(id="main-content"):
            with TabPane("Directories", id="dirs-tab"):
                with Horizontal(id="dirs-tab-content"):
                    with Vertical(id="dir-browser-container"):
                        yield Label("Browser")
                        with Horizontal(id="dir-nav-buttons"):
                            yield Button("..", id="parent-dir-btn")
                            yield Button("Add Selected (a)", id="add-dir-btn", variant="primary")
                        yield FilteredDirectoryTree(Path.cwd(), id="dir-tree")
                        with Horizontal(id="path-input-row"):
                            yield Input(placeholder="/path/to/add", id="path-input")
                            yield Button("+", id="add-path-btn", variant="success")
                    with Vertical(id="bound-dirs-container"):
                        yield Label("Bound Directories (click ro/rw to toggle)")
                        yield VerticalScroll(*dir_items, id="bound-dirs-list")

            with TabPane("Environment", id="env-tab"):
                with Vertical(id="env-tab-content"):
                    with Horizontal(id="env-buttons-row"):
                        yield Button("+ Add Variables", id="add-env-btn", variant="success")
                        yield Button("Clear System Env", id="toggle-clear-btn", variant="error")
                    with VerticalScroll(id="env-grid-scroll"):
                        yield Static("Sandbox will inherit all checked environment variables. Use Clear All to start with an empty environment.", id="env-hint")
                        with Horizontal(id="env-grid"):
                            # Split env vars into 3 columns
                            env_items = sorted(os.environ.items())
                            third = max(1, len(env_items) // 3)
                            for col_items in [env_items[:third], env_items[third:third*2], env_items[third*2:]]:
                                with Vertical(classes="env-column"):
                                    for name, value in col_items:
                                        yield EnvVarItem(name, value, self._toggle_env_var)

            with TabPane("File Systems", id="filesystems-tab"):
                with VerticalScroll(id="filesystems-tab-content"):
                    with Horizontal(id="options-grid"):
                        with Vertical(classes="options-column"):
                            with Container(classes="options-section"):
                                yield Label("Virtual Filesystems", classes="section-label")
                                yield DevModeCard(self._on_dev_mode_change)
                                yield OptionCard("/proc", "Process info filesystem", "opt-proc", True)
                                yield OptionCard("/tmp", "Ephemeral temp storage", "opt-tmp", True)
                                yield Label("Tmpfs size:")
                                yield Input(placeholder="default (half of RAM)", id="opt-tmpfs-size")
                        with Vertical(classes="options-column"):
                            with Container(classes="options-section"):
                                yield Label("System Paths (read-only)", classes="section-label")
                                yield OptionCard("/usr", "Programs and libraries", "opt-usr", True)
                                yield OptionCard("/bin", "Essential binaries", "opt-bin", True)
                                yield OptionCard("/lib", "Shared libraries", "opt-lib", True)
                                yield OptionCard("/lib64", "64-bit libraries", "opt-lib64", Path("/lib64").exists())
                                yield OptionCard("/sbin", "System binaries", "opt-sbin", True)
                                yield OptionCard("/etc", "Config files - RISKY!", "opt-etc", False)

            with TabPane("Overlays", id="overlays-tab"):
                with Vertical(id="overlays-tab-content"):
                    yield Static(
                        "Overlays make directories appear writable without changing originals.\n\n"
                        "  tmpfs      Changes discarded on exit\n"
                        "  persistent Changes saved to write dir\n\n"
                        "Example: source=/usr, mount=/usr, mode=tmpfs\n"
                        "         Sandbox can 'install' packages, real /usr untouched.",
                        id="overlay-hint")
                    yield Button("+ Add Overlay", id="add-overlay-btn", variant="success")
                    with Horizontal(id="overlay-header", classes="hidden"):
                        yield Static("Mode", classes="overlay-header-mode")
                        yield Static("Source (real directory)", classes="overlay-header-src")
                        yield Static("", classes="overlay-header-arrow")
                        yield Static("Mount point (in sandbox)", classes="overlay-header-dest")
                        yield Static("Write dir (persistent only)", classes="overlay-header-write")
                        yield Static("", classes="overlay-header-remove")
                    yield VerticalScroll(id="overlays-list")

            with TabPane("Sandbox", id="sandbox-tab"):
                with VerticalScroll(id="sandbox-tab-content"):
                    with Horizontal(id="options-grid"):
                        with Vertical(classes="options-column"):
                            with Container(classes="options-section"):
                                yield Label("Isolation", classes="section-label")
                                yield OptionCard("User namespace", "Appear as different user inside", "opt-unshare-user", False)
                                with Container(id="uid-gid-options", classes="hidden"):
                                    yield Label("UID:")
                                    yield Input(value=str(os.getuid()), id="opt-uid")
                                    yield Label("GID:")
                                    yield Input(value=str(os.getgid()), id="opt-gid")
                                yield OptionCard("PID namespace", "Hide host processes", "opt-unshare-pid", False)
                                yield OptionCard("IPC namespace", "Isolated shared memory", "opt-unshare-ipc", False)
                                yield OptionCard("UTS namespace", "Own hostname inside", "opt-unshare-uts", False)
                                yield OptionCard("Cgroup namespace", "Isolated resource limits", "opt-unshare-cgroup", False)
                                yield OptionCard("Disable nested sandboxing", "Prevent user namespaces inside", "opt-disable-userns", False)
                            with Container(classes="options-section"):
                                yield Label("Process", classes="section-label")
                                yield OptionCard("Kill with parent", "Dies when terminal closes", "opt-die-with-parent", True)
                                yield OptionCard("New session", "Prevents terminal escape attacks, but disables job control", "opt-new-session", True)
                                yield OptionCard("Run as PID 1", "Command runs as init process in PID namespace", "opt-as-pid-1", False)
                                yield Label("Working dir:")
                                yield Input(value=str(Path.cwd()), id="opt-chdir")
                                yield Label("Custom hostname:")
                                yield Input(placeholder="sandbox", id="opt-hostname")
                        with Vertical(classes="options-column"):
                            with Container(classes="options-section"):
                                yield Label("Network", classes="section-label")
                                yield OptionCard("Allow network", "Enable host network access", "opt-net", False)
                                yield OptionCard("DNS config", "/etc/resolv.conf for hostname resolution", "opt-resolv-conf", False)
                                yield OptionCard("SSL certificates", "/etc/ssl/certs for HTTPS", "opt-ssl-certs", False)
                            with Container(classes="options-section"):
                                yield Label("Desktop Integration", classes="section-label")
                                # Detect what's available
                                display_info = detect_display_server()
                                dbus_paths = detect_dbus_session()
                                dbus_desc = "Open browser, notifications, etc." if dbus_paths else "Not detected"
                                yield OptionCard("D-Bus session", dbus_desc, "opt-dbus", False)
                                if display_info["type"] == "wayland":
                                    display_desc = "Wayland display access"
                                elif display_info["type"] == "x11":
                                    display_desc = "X11 display access"
                                elif display_info["type"] == "both":
                                    display_desc = "X11 + Wayland display access"
                                else:
                                    display_desc = "No display detected"
                                yield OptionCard("Display server", display_desc, "opt-display", False)
                                yield OptionCard("User config", "~/.config for default apps, themes", "opt-user-config", False)

            with TabPane("Summary", id="summary-tab"):
                with Vertical(id="summary-tab-content"):
                    yield Static(f"Bubblewrap TUI\nVersion {self.version}", id="summary-header")
                    yield Label("Command Preview", classes="section-label")
                    yield Static(self._format_command(), id="command-preview")
                    yield Label("Summary", classes="section-label")
                    yield Static(self.config.get_explanation(), id="explanation")

        yield Horizontal(
            Static("", id="status-bar"),
            Button("Execute [Enter]", id="execute-btn", variant="success"),
            Button("Cancel [Esc]", id="cancel-btn", variant="error"),
            id="footer-buttons",
        )

    def _set_status(self, message: str) -> None:
        """Set status bar message."""
        status = self.query_one("#status-bar", Static)
        status.update(message)

    def _on_dev_mode_change(self, mode: str) -> None:
        """Handle /dev mode change."""
        self.config.dev_mode = mode
        self._update_preview()

    def _add_overlay(self) -> None:
        """Add a new overlay configuration."""
        overlay = OverlayConfig(source="", dest="", mode="tmpfs")
        self.config.overlays.append(overlay)
        overlays_list = self.query_one("#overlays-list", VerticalScroll)
        overlays_list.mount(OverlayItem(overlay, self._update_preview, self._remove_overlay))
        # Show header when we have overlays
        self.query_one("#overlay-header").remove_class("hidden")
        self._update_preview()

    def _remove_overlay(self, item: OverlayItem) -> None:
        """Remove an overlay from the list."""
        if item.overlay in self.config.overlays:
            self.config.overlays.remove(item.overlay)
            item.remove()
            # Hide header when no overlays left
            if not self.config.overlays:
                self.query_one("#overlay-header").add_class("hidden")
            self._update_preview()
            self._set_status("Overlay removed")

    def _remove_bound_dir(self, item: BoundDirItem) -> None:
        """Remove a bound directory from the list."""
        if item.bound_dir in self.config.bound_dirs:
            self.config.bound_dirs.remove(item.bound_dir)
            item.remove()
            self._update_preview()
            self._set_status(f"Removed: {item.bound_dir.path}")

    def _toggle_env_var(self, name: str, keep: bool) -> None:
        """Toggle whether to keep an environment variable."""
        is_custom = name in self.config.custom_env_vars
        if keep:
            self.config.keep_env_vars.add(name)
            self.config.unset_env_vars.discard(name)
        else:
            self.config.keep_env_vars.discard(name)
            if is_custom:
                # Remove custom var entirely instead of unsetting
                del self.config.custom_env_vars[name]
            else:
                self.config.unset_env_vars.add(name)
        self._update_preview()

    def _format_command(self) -> str:
        """Format the command for display - compact single line."""
        args = self.config.build_command()
        return shlex.join(args)

    def _update_preview(self) -> None:
        """Update the command preview."""
        preview = self.query_one("#command-preview", Static)
        preview.update(self._format_command())
        explanation = self.query_one("#explanation", Static)
        explanation.update(self.config.get_explanation())

    def _sync_config_from_ui(self) -> None:
        """Sync the config from UI state."""
        try:
            # Filesystems (dev_mode is handled by callback)
            self.config.mount_proc = self.query_one("#opt-proc", Checkbox).value
            self.config.mount_tmp = self.query_one("#opt-tmp", Checkbox).value

            # Network
            self.config.share_net = self.query_one("#opt-net", Checkbox).value
            self.config.bind_resolv_conf = self.query_one("#opt-resolv-conf", Checkbox).value
            self.config.bind_ssl_certs = self.query_one("#opt-ssl-certs", Checkbox).value

            # Desktop integration
            self.config.allow_dbus = self.query_one("#opt-dbus", Checkbox).value
            self.config.allow_display = self.query_one("#opt-display", Checkbox).value
            self.config.bind_user_config = self.query_one("#opt-user-config", Checkbox).value

            # Namespaces
            self.config.unshare_user = self.query_one("#opt-unshare-user", Checkbox).value
            self.config.unshare_pid = self.query_one("#opt-unshare-pid", Checkbox).value
            self.config.unshare_ipc = self.query_one("#opt-unshare-ipc", Checkbox).value
            self.config.unshare_uts = self.query_one("#opt-unshare-uts", Checkbox).value
            self.config.unshare_cgroup = self.query_one("#opt-unshare-cgroup", Checkbox).value

            # Process
            self.config.die_with_parent = self.query_one("#opt-die-with-parent", Checkbox).value
            self.config.new_session = self.query_one("#opt-new-session", Checkbox).value
            self.config.as_pid_1 = self.query_one("#opt-as-pid-1", Checkbox).value
            self.config.chdir = self.query_one("#opt-chdir", Input).value
            self.config.custom_hostname = self.query_one("#opt-hostname", Input).value

            # UID/GID (shown when user namespace is enabled)
            try:
                self.config.uid = int(self.query_one("#opt-uid", Input).value)
            except ValueError:
                pass
            try:
                self.config.gid = int(self.query_one("#opt-gid", Input).value)
            except ValueError:
                pass
            self.config.disable_userns = self.query_one("#opt-disable-userns", Checkbox).value
            self.config.tmpfs_size = self.query_one("#opt-tmpfs-size", Input).value.strip()

            # System binds
            self.config.bind_usr = self.query_one("#opt-usr", Checkbox).value
            self.config.bind_bin = self.query_one("#opt-bin", Checkbox).value
            self.config.bind_lib = self.query_one("#opt-lib", Checkbox).value
            self.config.bind_lib64 = self.query_one("#opt-lib64", Checkbox).value
            self.config.bind_sbin = self.query_one("#opt-sbin", Checkbox).value
            self.config.bind_etc = self.query_one("#opt-etc", Checkbox).value
        except Exception:
            pass  # Widgets not ready yet

    @on(Checkbox.Changed)
    def on_checkbox_changed(self, event: Checkbox.Changed) -> None:
        """Handle checkbox changes."""
        # Auto-enable DNS and SSL certs when network is toggled on
        if event.checkbox.id == "opt-net" and event.value:
            try:
                self.query_one("#opt-resolv-conf", Checkbox).value = True
                self.query_one("#opt-ssl-certs", Checkbox).value = True
            except Exception:
                pass
        # Show/hide UID/GID options when user namespace is toggled
        if event.checkbox.id == "opt-unshare-user":
            try:
                uid_gid = self.query_one("#uid-gid-options")
                if event.value:
                    uid_gid.remove_class("hidden")
                else:
                    uid_gid.add_class("hidden")
            except Exception:
                pass
        self._sync_config_from_ui()
        self._update_preview()

    @on(Input.Changed)
    def on_input_changed(self, event: Input.Changed) -> None:
        """Handle input changes."""
        self._sync_config_from_ui()
        self._update_preview()

    @on(Button.Pressed, "#add-overlay-btn")
    def on_add_overlay_pressed(self, event: Button.Pressed) -> None:
        """Add a new overlay."""
        self._add_overlay()

    @on(Button.Pressed, "#add-dir-btn")
    def on_add_dir_pressed(self, event: Button.Pressed) -> None:
        """Add the selected directory."""
        self.action_add_directory()

    @on(Button.Pressed, "#parent-dir-btn")
    def on_parent_dir_pressed(self, event: Button.Pressed) -> None:
        """Navigate to parent directory."""
        tree = self.query_one("#dir-tree", FilteredDirectoryTree)
        current = tree.path
        parent = current.parent
        if parent != current:
            tree.path = parent

    @on(Button.Pressed, "#add-path-btn")
    def on_add_path_pressed(self, event: Button.Pressed) -> None:
        """Add a path from the input field."""
        self._add_path_from_input()

    @on(Input.Submitted, "#path-input")
    def on_path_input_submitted(self, event: Input.Submitted) -> None:
        """Handle Enter in path input."""
        self._add_path_from_input()

    def _add_path_from_input(self) -> None:
        """Add a path from the input field."""
        path_input = self.query_one("#path-input", Input)
        path_str = path_input.value.strip()
        if not path_str:
            return
        path = Path(path_str).expanduser().resolve()
        if not path.exists():
            self._set_status(f"Path does not exist: {path}")
            return
        if not path.is_dir():
            self._set_status(f"Not a directory: {path}")
            return
        # Check if already added
        for bd in self.config.bound_dirs:
            if bd.path == path:
                self._set_status(f"Already added: {path}")
                return
        bound_dir = BoundDirectory(path=path, readonly=True)
        self.config.bound_dirs.append(bound_dir)
        dirs_list = self.query_one("#bound-dirs-list", VerticalScroll)
        dirs_list.mount(BoundDirItem(bound_dir, self._update_preview, self._remove_bound_dir))
        path_input.value = ""
        self._update_preview()
        self._set_status(f"Added: {path}")

    @on(Button.Pressed, "#toggle-clear-btn")
    def on_toggle_clear_pressed(self, event: Button.Pressed) -> None:
        """Toggle between clear and restore environment."""
        btn = self.query_one("#toggle-clear-btn", Button)
        if not self.config.clear_env:
            # Clear environment
            self.config.clear_env = True
            self.config.keep_env_vars = set(self.config.custom_env_vars.keys())
            # Hide system env grid, keep custom vars
            self.query_one("#env-grid-scroll").add_class("hidden")
            btn.label = "Restore System Env"
            btn.variant = "primary"
            self._update_preview()
            self._set_status("System environment cleared")
        else:
            # Restore environment
            self.config.clear_env = False
            self.config.keep_env_vars = set(os.environ.keys()) | set(self.config.custom_env_vars.keys())
            self.config.unset_env_vars.clear()
            # Show env grid
            self.query_one("#env-grid-scroll").remove_class("hidden")
            # Check all env var checkboxes
            for item in self.query(EnvVarItem):
                checkbox = item.query_one(".env-keep-toggle", Checkbox)
                checkbox.value = True
            btn.label = "Clear System Env"
            btn.variant = "error"
            self._update_preview()
            self._set_status("System environment restored")

    @on(Button.Pressed, "#add-env-btn")
    def on_add_env_pressed(self, event: Button.Pressed) -> None:
        """Open dialog to add environment variables."""
        self.push_screen(AddEnvDialog(), self._handle_add_env_result)

    def _handle_add_env_result(self, pairs: list[tuple[str, str]]) -> None:
        """Handle result from add env dialog."""
        if not pairs:
            return
        for name, value in pairs:
            self.config.custom_env_vars[name] = value
            self.config.keep_env_vars.add(name)
        # Only show env grid if not in cleared state, or if we have custom vars to show
        if self.config.custom_env_vars:
            self.query_one("#env-grid-scroll").remove_class("hidden")
        self._reflow_env_columns()
        self._update_preview()
        self._set_status(f"Added {len(pairs)} variable(s)")

    def _reflow_env_columns(self) -> None:
        """Reflow environment variable items across columns."""
        # Remove all existing items
        for item in self.query(EnvVarItem):
            item.remove()

        # Build list based on clear_env state
        if self.config.clear_env:
            # Only show custom vars when system env is cleared
            all_vars = [(n, v) for n, v in self.config.custom_env_vars.items()]
        else:
            # Show custom vars first, then sorted system vars
            all_vars = [(n, v) for n, v in self.config.custom_env_vars.items()]
            all_vars += sorted(os.environ.items())

        # Get column containers
        columns = list(self.query(".env-column"))
        if not columns or not all_vars:
            return

        # Distribute across columns
        third = max(1, len(all_vars) // 3)
        col_items = [all_vars[:third], all_vars[third:third*2], all_vars[third*2:]]

        for col_idx, col in enumerate(columns):
            if col_idx < len(col_items):
                for name, value in col_items[col_idx]:
                    is_kept = name in self.config.keep_env_vars
                    item = EnvVarItem(name, value, self._toggle_env_var)
                    col.mount(item)
                    # Set checkbox state after mount
                    checkbox = item.query_one(".env-keep-toggle", Checkbox)
                    checkbox.value = is_kept

    @on(Button.Pressed, "#execute-btn")
    def on_execute_pressed(self, event: Button.Pressed) -> None:
        """Execute the command."""
        self.action_execute()

    @on(Button.Pressed, "#cancel-btn")
    def on_cancel_pressed(self, event: Button.Pressed) -> None:
        """Cancel and exit."""
        self.action_cancel()

    def action_add_directory(self) -> None:
        """Add the currently selected directory to the bound list."""
        tree = self.query_one("#dir-tree", FilteredDirectoryTree)
        if tree.cursor_node and tree.cursor_node.data:
            path = tree.cursor_node.data.path if hasattr(tree.cursor_node.data, 'path') else tree.cursor_node.data
            if isinstance(path, Path) and path.is_dir():
                # Check if already added
                for bd in self.config.bound_dirs:
                    if bd.path == path:
                        self._set_status(f"Already added: {path}")
                        return

                bound_dir = BoundDirectory(path=path, readonly=True)
                self.config.bound_dirs.append(bound_dir)

                dirs_list = self.query_one("#bound-dirs-list", VerticalScroll)
                dirs_list.mount(BoundDirItem(bound_dir, self._update_preview, self._remove_bound_dir))

                self._update_preview()
                self._set_status(f"Added: {path}")

    def action_execute(self) -> None:
        """Execute the configured command."""
        self._execute_command = True
        self.exit()

    def action_cancel(self) -> None:
        """Cancel and exit without executing."""
        self._execute_command = False
        self.exit()
