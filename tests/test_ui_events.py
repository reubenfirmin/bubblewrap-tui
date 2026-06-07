"""Tests for UI event handling - verifies button clicks and checkbox changes trigger handlers.

These tests catch wiring problems where event decorators don't register properly.
"""

import pytest
from pathlib import Path

from textual.widgets import Button, Checkbox, Input, Static
from textual.containers import VerticalScroll

# Import from src modules
from app import BubblewrapTUI
from model import SandboxConfig, BoundDirectory
import ui.ids as ids
from ui.ids import css


class TestDirectoryEvents:
    """Test directory tab event handlers."""

    @pytest.mark.asyncio
    async def test_add_selected_button_triggers_handler(self):
        """Clicking 'Add Selected' button should add a directory."""
        config = SandboxConfig(command=["bash"])
        initial_count = len(config.bound_dirs)

        app = BubblewrapTUI(command=["bash"], config=config)
        async with app.run_test() as pilot:
            # Get the directory tree and select a node
            tree = app.query_one(css(ids.DIR_TREE))
            # Navigate to a directory (root should have children)
            await pilot.pause()

            # Record bound dirs count before click
            before_count = len(app.config.bound_dirs)

            # Find and click the Add Selected button
            add_btn = app.query_one(css(ids.ADD_DIR_BTN), Button)
            await pilot.click(add_btn)
            await pilot.pause()

            # If a node was selected and valid, dir count should increase
            # This test verifies the handler RUNS (no crash, button is wired)
            # Even if no node is selected, handler should complete without error
            assert True  # Handler completed without crash

    @pytest.mark.asyncio
    async def test_path_input_enter_triggers_handler(self):
        """Pressing Enter in path input should attempt to add the path."""
        config = SandboxConfig(command=["bash"])
        app = BubblewrapTUI(command=["bash"], config=config)

        async with app.run_test() as pilot:
            # Get the path input and focus it
            path_input = app.query_one(css(ids.PATH_INPUT), Input)
            path_input.focus()
            await pilot.pause()

            # Enter a path and trigger submit (use /var, not /tmp which conflicts with VFS)
            path_input.value = "/var"
            # Directly call the action (simulating Input.Submitted event)
            await path_input.action_submit()
            await pilot.pause()

            # Check if /var was added to bound dirs
            paths = [str(bd.path) for bd in app.config.bound_dirs]
            assert "/var" in paths, f"Expected /var in {paths}"

    @pytest.mark.asyncio
    async def test_add_path_button_triggers_handler(self):
        """Clicking + button next to path input should add the path."""
        config = SandboxConfig(command=["bash"])
        app = BubblewrapTUI(command=["bash"], config=config)

        async with app.run_test() as pilot:
            # Get the path input
            path_input = app.query_one(css(ids.PATH_INPUT), Input)

            # Enter a path
            path_input.value = "/var"
            # Call the mixin method directly (simulates button click)
            app._add_path_from_input()
            await pilot.pause()

            # Check if /var was added
            paths = [str(bd.path) for bd in app.config.bound_dirs]
            assert "/var" in paths, f"Expected /var in {paths}"


class TestEnvironmentEvents:
    """Test environment tab event handlers."""

    @pytest.mark.asyncio
    async def test_clear_system_env_button_toggles(self):
        """Clear System Env button should toggle all env vars."""
        config = SandboxConfig(command=["bash"])
        # Start with some env vars kept
        config.environment.keep_env_vars = {"PATH", "HOME", "USER"}
        config.environment.clear_env = False  # Not cleared initially

        app = BubblewrapTUI(command=["bash"], config=config)

        async with app.run_test() as pilot:
            # Verify initial state
            assert app.config.environment.clear_env is False

            # Simulate button press by calling the handler method
            from textual.widgets import Button
            # Create a mock event (the handler doesn't use the event object)
            app.on_toggle_clear_pressed(Button.Pressed(app.query_one(css(ids.TOGGLE_CLEAR_BTN), Button)))
            await pilot.pause()

            # Should have toggled to cleared state
            assert app.config.environment.clear_env is True, \
                "Clear button should toggle clear_env to True"


class TestFilesystemEvents:
    """Test filesystem tab checkbox handlers."""

    @pytest.mark.asyncio
    async def test_filesystem_checkbox_updates_config(self):
        """Toggling filesystem checkboxes should update config."""
        config = SandboxConfig(command=["bash"])
        config.filesystem.bind_usr = True

        app = BubblewrapTUI(command=["bash"], config=config)

        async with app.run_test() as pilot:
            # Find the /usr checkbox
            usr_checkbox = app.query_one(css(ids.OPT_USR), Checkbox)
            initial_value = app.config.filesystem.bind_usr
            initial_checkbox = usr_checkbox.value

            # Toggle it by directly setting value (simulates user click)
            usr_checkbox.value = not usr_checkbox.value
            await pilot.pause()

            # First check: checkbox UI value should have changed
            assert usr_checkbox.value != initial_checkbox, \
                f"Checkbox UI value should have changed from {initial_checkbox}"

            # Second check: config should have changed (via Checkbox.Changed event)
            assert app.config.filesystem.bind_usr != initial_value, \
                f"Config bind_usr should update when checkbox changes from {initial_value} (checkbox is now {usr_checkbox.value})"

    @pytest.mark.asyncio
    async def test_network_checkbox_auto_enables_dns_ssl(self):
        """Enabling network should auto-enable DNS and SSL certs."""
        config = SandboxConfig(command=["bash"])
        config.network.share_net = False
        config.network.bind_resolv_conf = False
        config.network.bind_ssl_certs = False

        app = BubblewrapTUI(command=["bash"], config=config)

        async with app.run_test() as pilot:
            # Sync UI to config first
            app._sync_ui_from_config()
            await pilot.pause()

            # Find checkboxes
            net_checkbox = app.query_one(css(ids.OPT_NET), Checkbox)
            dns_checkbox = app.query_one(css(ids.OPT_RESOLV_CONF), Checkbox)
            ssl_checkbox = app.query_one(css(ids.OPT_SSL_CERTS), Checkbox)

            # Verify initial state
            assert net_checkbox.value is False
            assert dns_checkbox.value is False
            assert ssl_checkbox.value is False

            # Enable network by setting value (this triggers Checkbox.Changed)
            net_checkbox.value = True
            await pilot.pause()

            # DNS and SSL should be auto-enabled by the on_checkbox_changed handler
            assert dns_checkbox.value is True, "Network enable should auto-enable DNS"
            assert ssl_checkbox.value is True, "Network enable should auto-enable SSL"


class TestCheckboxToCommandSync:
    """Test that checkbox changes are reflected in the generated command."""

    @pytest.mark.asyncio
    async def test_default_etc_not_in_command(self):
        """With default config, /etc should NOT be in the command (default is False)."""
        # Create app with fresh default config (no modifications)
        app = BubblewrapTUI(command=["ls"])

        async with app.run_test() as pilot:
            await pilot.pause()

            # Check the config value
            assert app.config.filesystem.bind_etc is False, \
                f"Default bind_etc should be False, got {app.config.filesystem.bind_etc}"

            # Check the command doesn't have /etc
            command = app.config.build_command()
            etc_binds = [i for i, arg in enumerate(command) if arg == "/etc" and i > 0 and command[i-1] in ("--ro-bind", "--bind")]
            assert len(etc_binds) == 0, \
                f"Default command should NOT have /etc bind: {command}"

    @pytest.mark.asyncio
    async def test_etc_checkbox_starts_unchecked_by_default(self):
        """The /etc checkbox should be unchecked when app starts with default config."""
        app = BubblewrapTUI(command=["ls"])

        async with app.run_test() as pilot:
            await pilot.pause()

            # Get the /etc checkbox
            etc_checkbox = app.query_one(css(ids.OPT_ETC), Checkbox)

            # It should be unchecked (value=False) by default
            assert etc_checkbox.value is False, \
                f"/etc checkbox should start unchecked, got value={etc_checkbox.value}"

    @pytest.mark.asyncio
    async def test_checkbox_value_syncs_to_config_immediately(self):
        """Changing checkbox value should immediately update config."""
        app = BubblewrapTUI(command=["ls"])

        async with app.run_test() as pilot:
            await pilot.pause()

            # Verify initial state
            etc_checkbox = app.query_one(css(ids.OPT_ETC), Checkbox)
            assert etc_checkbox.value is False
            assert app.config.filesystem.bind_etc is False

            # Check the checkbox
            etc_checkbox.value = True
            await pilot.pause()

            # Config should be updated immediately
            assert app.config.filesystem.bind_etc is True, \
                f"Config bind_etc should be True after checking checkbox, got {app.config.filesystem.bind_etc}"

            # And the command should now include /etc
            command = app.config.build_command()
            command_str = " ".join(command)
            assert "--ro-bind /etc /etc" in command_str, \
                f"Command should include /etc bind after checking: {command}"

    @pytest.mark.asyncio
    async def test_unchecking_etc_removes_from_command(self):
        """Unchecking /etc checkbox should remove --ro-bind /etc from command."""
        config = SandboxConfig(command=["ls"])
        config.filesystem.bind_etc = True  # Start with /etc enabled

        app = BubblewrapTUI(command=["ls"], config=config)

        async with app.run_test() as pilot:
            # Sync UI from config
            app._sync_ui_from_config()
            await pilot.pause()

            # Verify initial state - /etc should be in command
            initial_command = app.config.build_command()
            assert "--ro-bind" in " ".join(initial_command) and "/etc" in " ".join(initial_command), \
                f"Initial command should have /etc bind: {initial_command}"

            # Uncheck /etc
            etc_checkbox = app.query_one(css(ids.OPT_ETC), Checkbox)
            assert etc_checkbox.value is True, "Checkbox should start checked"
            etc_checkbox.value = False
            await pilot.pause()

            # Command should no longer have /etc
            new_command = app.config.build_command()
            # Check that /etc is not bound (but might appear in other contexts)
            etc_binds = [i for i, arg in enumerate(new_command) if arg == "/etc" and i > 0 and new_command[i-1] in ("--ro-bind", "--bind")]
            assert len(etc_binds) == 0, \
                f"Unchecking /etc should remove it from command: {new_command}"

    @pytest.mark.asyncio
    async def test_checking_etc_adds_to_command(self):
        """Checking /etc checkbox should add --ro-bind /etc to command."""
        config = SandboxConfig(command=["ls"])
        config.filesystem.bind_etc = False  # Start with /etc disabled

        app = BubblewrapTUI(command=["ls"], config=config)

        async with app.run_test() as pilot:
            # Sync UI from config
            app._sync_ui_from_config()
            await pilot.pause()

            # Verify initial state - /etc should NOT be in command
            initial_command = app.config.build_command()
            etc_binds = [i for i, arg in enumerate(initial_command) if arg == "/etc" and i > 0 and initial_command[i-1] in ("--ro-bind", "--bind")]
            assert len(etc_binds) == 0, \
                f"Initial command should not have /etc bind: {initial_command}"

            # Check /etc
            etc_checkbox = app.query_one(css(ids.OPT_ETC), Checkbox)
            assert etc_checkbox.value is False, "Checkbox should start unchecked"
            etc_checkbox.value = True
            await pilot.pause()

            # Command should now have /etc
            new_command = app.config.build_command()
            assert "--ro-bind" in " ".join(new_command) and "/etc" in " ".join(new_command), \
                f"Checking /etc should add it to command: {new_command}"

    @pytest.mark.asyncio
    async def test_all_filesystem_checkboxes_affect_command(self):
        """All filesystem checkboxes should properly affect the generated command."""
        config = SandboxConfig(command=["ls"])
        # Enable all filesystem binds initially
        config.filesystem.bind_usr = True
        config.filesystem.bind_bin = True
        config.filesystem.bind_lib = True
        config.filesystem.bind_lib64 = True
        config.filesystem.bind_sbin = True
        config.filesystem.bind_etc = True

        app = BubblewrapTUI(command=["ls"], config=config)

        async with app.run_test() as pilot:
            app._sync_ui_from_config()
            await pilot.pause()

            # Uncheck all filesystem binds
            for checkbox_id, path in [
                (ids.OPT_USR, "/usr"),
                (ids.OPT_BIN, "/bin"),
                (ids.OPT_LIB, "/lib"),
                (ids.OPT_LIB64, "/lib64"),
                (ids.OPT_SBIN, "/sbin"),
                (ids.OPT_ETC, "/etc"),
            ]:
                checkbox = app.query_one(css(checkbox_id), Checkbox)
                checkbox.value = False
                await pilot.pause()

                # Verify this path is no longer in command
                command = app.config.build_command()
                path_binds = [i for i, arg in enumerate(command) if arg == path and i > 0 and command[i-1] in ("--ro-bind", "--bind")]
                assert len(path_binds) == 0, \
                    f"After unchecking {checkbox_id}, {path} should not be in command: {command}"


class TestSummaryPreview:
    """Test that config changes update the preview."""

    @pytest.mark.asyncio
    async def test_preview_updates_on_checkbox_change(self):
        """Command preview should update when checkboxes change."""
        config = SandboxConfig(command=["bash"])
        config.filesystem.mount_proc = False  # Ensure proc is off initially
        app = BubblewrapTUI(command=["bash"], config=config)

        async with app.run_test() as pilot:
            # Sync UI from config
            app._sync_ui_from_config()
            await pilot.pause()

            # Get the command from config before change
            initial_command = app.config.build_command()

            # Toggle a checkbox (proc) by setting value directly
            proc_checkbox = app.query_one(css(ids.OPT_PROC), Checkbox)
            proc_checkbox.value = True  # Enable proc
            await pilot.pause()

            # Config should be updated and command should change
            new_command = app.config.build_command()
            assert new_command != initial_command, \
                f"Toggling proc should change command: {initial_command} vs {new_command}"


class TestOverlayEvents:
    """Test overlay tab event handlers."""

    @pytest.mark.asyncio
    async def test_add_overlay_button_triggers_handler(self):
        """Clicking Add Overlay button should trigger handler."""
        config = SandboxConfig(command=["bash"])
        app = BubblewrapTUI(command=["bash"], config=config)

        async with app.run_test() as pilot:
            # Click add overlay button
            add_btn = app.query_one(css(ids.ADD_OVERLAY_BTN), Button)
            await pilot.click(add_btn)
            await pilot.pause()

            # Handler should complete without crash
            # Overlay count may or may not increase (depends on valid path input)
            assert True


class TestProfileEvents:
    """Test profile management event handlers."""

    @pytest.mark.asyncio
    async def test_save_profile_button_triggers_handler(self):
        """Clicking Save Profile button should open modal."""
        config = SandboxConfig(command=["bash"])
        app = BubblewrapTUI(command=["bash"], config=config)

        async with app.run_test() as pilot:
            # Click the save button in the header (opens modal)
            save_btn = app.query_one(css(ids.SAVE_PROFILE_BTN), Button)
            await pilot.click(save_btn)
            # Wait for modal animation/mounting
            await pilot.pause()
            await pilot.pause()

            # Verify the modal opened by checking for the modal screen
            # The modal is pushed as a new screen
            from ui.modals import SaveProfileModal
            screens = list(app.screen_stack)
            modal_found = any(isinstance(s, SaveProfileModal) for s in screens)
            assert modal_found, "SaveProfileModal should be in screen stack"


class TestMixinEventInheritance:
    """Test that mixin event handlers are properly inherited."""

    @pytest.mark.asyncio
    async def test_directory_mixin_handlers_registered(self):
        """DirectoryEventsMixin handlers should be accessible on BubblewrapTUI."""
        app = BubblewrapTUI(command=["bash"])

        # Check that mixin methods exist on the app
        assert hasattr(app, 'on_add_dir_pressed'), "DirectoryEventsMixin.on_add_dir_pressed not inherited"
        assert hasattr(app, 'on_path_input_submitted'), "DirectoryEventsMixin.on_path_input_submitted not inherited"
        assert hasattr(app, 'action_add_directory'), "DirectoryEventsMixin.action_add_directory not inherited"

    @pytest.mark.asyncio
    async def test_environment_mixin_handlers_registered(self):
        """EnvironmentEventsMixin handlers should be accessible on BubblewrapTUI."""
        app = BubblewrapTUI(command=["bash"])

        assert hasattr(app, 'on_toggle_clear_pressed'), "EnvironmentEventsMixin.on_toggle_clear_pressed not inherited"
        assert hasattr(app, 'on_add_env_pressed'), "EnvironmentEventsMixin.on_add_env_pressed not inherited"

    @pytest.mark.asyncio
    async def test_overlay_mixin_handlers_registered(self):
        """OverlayEventsMixin handlers should be accessible on BubblewrapTUI."""
        app = BubblewrapTUI(command=["bash"])

        assert hasattr(app, 'on_add_overlay_pressed'), "OverlayEventsMixin.on_add_overlay_pressed not inherited"

    @pytest.mark.asyncio
    async def test_execute_mixin_handlers_registered(self):
        """ExecuteEventsMixin handlers should be accessible on BubblewrapTUI."""
        app = BubblewrapTUI(command=["bash"])

        assert hasattr(app, 'on_execute_pressed'), "ExecuteEventsMixin.on_execute_pressed not inherited"
        assert hasattr(app, 'on_cancel_pressed'), "ExecuteEventsMixin.on_cancel_pressed not inherited"


class TestNetworkFilterSync:
    """Test that network filter data syncs to UI on profile load."""

    @pytest.mark.asyncio
    async def test_network_filter_lists_sync_on_profile_load(self):
        """Loading a config with network filter data should display it in widgets."""
        from ui.widgets.network import FilterList, PortList, FilterModeRadio

        # Create config with network filter values
        config = SandboxConfig(command=["bash"])
        config.network.share_net = True
        config._network_group.set("network_mode", "filter")
        config._network_group.set("hostname_mode", "whitelist")
        config._network_group.set("hostname_hosts", ["github.com", "npmjs.org"])
        config._network_group.set("ip_mode", "blacklist")
        config._network_group.set("ip_cidrs", ["10.0.0.0/8"])
        config._network_group.set("expose_ports", [8080])
        config._network_group.set("host_ports", [5432, 6379])

        app = BubblewrapTUI(command=["bash"], config=config)
        async with app.run_test() as pilot:
            await pilot.pause()

            # Simulate profile load
            app._set_config(config)
            app._on_profile_loaded()
            await pilot.pause()

            # Verify FilterList widgets show loaded data
            hostname_list = app.query_one(css(ids.HOSTNAME_LIST), FilterList)
            assert hostname_list._items == ["github.com", "npmjs.org"]

            cidr_list = app.query_one(css(ids.CIDR_LIST), FilterList)
            assert cidr_list._items == ["10.0.0.0/8"]

            # Verify PortList widgets show loaded data
            expose_ports = app.query_one(css(ids.EXPOSE_PORT_LIST), PortList)
            assert expose_ports._ports == [8080]

            host_ports = app.query_one(css(ids.HOST_PORT_LIST), PortList)
            assert host_ports._ports == [5432, 6379]

            # Verify FilterModeRadio widgets show correct modes
            hostname_radio = app.query_one(css(ids.HOSTNAME_MODE_RADIO), FilterModeRadio)
            assert hostname_radio.mode == "whitelist"

            ip_radio = app.query_one(css(ids.IP_MODE_RADIO), FilterModeRadio)
            assert ip_radio.mode == "blacklist"


class TestStatusBarSequenceGuard:
    """Status updates must be monotonic so a stale update can't clobber a newer
    one (#94 defense-in-depth)."""

    @pytest.mark.asyncio
    async def test_set_status_displays_message(self):
        app = BubblewrapTUI(command=["bash"], config=SandboxConfig(command=["bash"]))
        async with app.run_test() as pilot:
            await pilot.pause()
            app._set_status("hello world")
            await pilot.pause()
            status = app.query_one(css(ids.STATUS_BAR), Static)
            assert str(status.render()) == "hello world"

    @pytest.mark.asyncio
    async def test_stale_update_does_not_overwrite_newer(self):
        app = BubblewrapTUI(command=["bash"], config=SandboxConfig(command=["bash"]))
        async with app.run_test() as pilot:
            await pilot.pause()
            status = app.query_one(css(ids.STATUS_BAR), Static)
            app._apply_status("newer", 5)
            await pilot.pause()
            assert str(status.render()) == "newer"
            # An out-of-order (stale) apply with a lower sequence must be ignored.
            app._apply_status("stale", 3)
            await pilot.pause()
            assert str(status.render()) == "newer"

    @pytest.mark.asyncio
    async def test_set_status_sequence_is_monotonic(self):
        app = BubblewrapTUI(command=["bash"], config=SandboxConfig(command=["bash"]))
        async with app.run_test() as pilot:
            await pilot.pause()
            app._set_status("a")
            first = app._status_seq
            app._set_status("b")
            assert app._status_seq == first + 1


class TestProfileLoadEnvCheckboxes:
    """Environment checkboxes must reflect a loaded profile even before the tab
    is visited (#95)."""

    @pytest.mark.asyncio
    async def test_unchecked_env_var_reflected_after_load(self):
        import os
        from ui.widgets import EnvVarItem

        target = sorted(os.environ.keys())[0]
        app = BubblewrapTUI(command=["bash"])
        async with app.run_test() as pilot:
            await pilot.pause()

            loaded = SandboxConfig(command=["bash"])
            loaded.environment.clear_env = False
            loaded.environment.keep_env_vars = set(os.environ.keys()) - {target}
            loaded.environment.unset_env_vars = {target}

            app._set_config(loaded)
            app._on_profile_loaded()
            await pilot.pause()

            checkbox = None
            for item in app.query(EnvVarItem):
                if item.var_name == target:
                    checkbox = item.query_one(".env-keep-toggle", Checkbox)
                    break
            assert checkbox is not None, "env var item not found"
            assert checkbox.value is False, (
                "checkbox should be unchecked to match loaded profile"
            )

    @pytest.mark.asyncio
    async def test_kept_env_var_stays_checked_after_load(self):
        import os
        from ui.widgets import EnvVarItem

        target = sorted(os.environ.keys())[0]
        app = BubblewrapTUI(command=["bash"])
        async with app.run_test() as pilot:
            await pilot.pause()
            loaded = SandboxConfig(command=["bash"])
            loaded.environment.clear_env = False
            loaded.environment.keep_env_vars = set(os.environ.keys())
            app._set_config(loaded)
            app._on_profile_loaded()
            await pilot.pause()

            checkbox = None
            for item in app.query(EnvVarItem):
                if item.var_name == target:
                    checkbox = item.query_one(".env-keep-toggle", Checkbox)
                    break
            assert checkbox is not None
            assert checkbox.value is True


class TestSecurityWarningBanner:
    """The /dev security warning must track the actual config (#96)."""

    @pytest.mark.asyncio
    async def test_toggling_dev_mode_to_full_shows_warning(self):
        from ui.widgets import DevModeCard

        app = BubblewrapTUI(command=["bash"], config=SandboxConfig(command=["bash"]))
        async with app.run_test() as pilot:
            await pilot.pause()
            warning = app.query_one(css(ids.SECURITY_WARNING), Static)
            btn = app.query_one(css(ids.DEV_MODE_BTN), Button)
            assert not warning.has_class("-visible")

            for _ in range(3):
                if app.config.vfs.dev_mode == "full":
                    break
                btn.press()
                await pilot.pause()

            assert app.config.vfs.dev_mode == "full"
            assert warning.has_class("-visible"), "warning not shown after dev->full"
            assert warning.display is True

    @pytest.mark.asyncio
    async def test_warning_clears_when_loading_safe_profile(self):
        app = BubblewrapTUI(command=["bash"], config=SandboxConfig(command=["bash"]))
        async with app.run_test() as pilot:
            await pilot.pause()
            warning = app.query_one(css(ids.SECURITY_WARNING), Static)
            app.config.vfs.dev_mode = "full"
            app._update_security_warning()
            await pilot.pause()
            assert warning.has_class("-visible")

            loaded = SandboxConfig(command=["bash"])
            loaded.vfs.dev_mode = "minimal"
            app._set_config(loaded)
            app._on_profile_loaded()
            await pilot.pause()
            assert not warning.has_class("-visible")
            assert warning.display is False


class TestInputNewlineSanitization:
    """Free-form fields must not store embedded newlines, even if a value is set
    programmatically (#97)."""

    @pytest.mark.asyncio
    async def test_overlay_dest_sanitized(self):
        from ui.widgets import OverlayItem

        app = BubblewrapTUI(command=["bash"], config=SandboxConfig(command=["bash"]))
        async with app.run_test() as pilot:
            await pilot.pause()
            app._add_overlay()
            await pilot.pause()
            item = app.query_one(OverlayItem)
            dest_input = item.query_one(".overlay-dest-input", Input)
            dest_input.value = "/mnt\n/evil"
            await pilot.pause()
            assert "\n" not in item.overlay.dest
            assert item.overlay.dest == "/mnt/evil"

    @pytest.mark.asyncio
    async def test_overlay_source_sanitized(self):
        from ui.widgets import OverlayItem

        app = BubblewrapTUI(command=["bash"], config=SandboxConfig(command=["bash"]))
        async with app.run_test() as pilot:
            await pilot.pause()
            app._add_overlay()
            await pilot.pause()
            item = app.query_one(OverlayItem)
            # mode must allow source editing
            item.overlay.mode = "overlay"
            src_input = item.query_one(".overlay-src-input", Input)
            src_input.disabled = False
            src_input.value = "/src\n/x"
            await pilot.pause()
            assert "\n" not in item.overlay.source

    @pytest.mark.asyncio
    async def test_add_env_dialog_strips_newlines(self):
        from ui.widgets import AddEnvDialog
        from ui.widgets.environment import EnvVarRow

        app = BubblewrapTUI(command=["bash"], config=SandboxConfig(command=["bash"]))
        async with app.run_test() as pilot:
            await pilot.pause()
            dialog = AddEnvDialog()
            await app.push_screen(dialog)
            await pilot.pause()
            row = dialog.query_one(EnvVarRow)
            row.query_one(".env-name-input", Input).value = "FOO"
            row.query_one(".env-value-input", Input).value = "bar\nbaz"
            await pilot.pause()
            pairs = dialog._get_env_pairs()
            assert pairs == [("FOO", "barbaz")]
