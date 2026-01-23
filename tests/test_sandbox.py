"""Tests for sandbox lifecycle management."""

from pathlib import Path
from unittest.mock import patch

import pytest


class TestInstallSandboxBinary:
    """Test install_sandbox_binary function."""

    def test_script_quotes_profile_with_spaces(self, tmp_path):
        """Profile names with spaces are properly quoted."""
        from sandbox import install_sandbox_binary

        # Set up mock sandbox directory with an executable
        sandbox_dir = tmp_path / "sandboxes" / "test"
        overlays_dir = sandbox_dir / "overlays" / "home-sandbox" / "bin"
        overlays_dir.mkdir(parents=True)
        exe = overlays_dir / "myapp"
        exe.write_text("#!/bin/sh\necho hello")
        exe.chmod(0o755)

        # Script goes to ~/.local/bin, so with mocked home it's tmp_path/.local/bin
        bin_dir = tmp_path / ".local" / "bin"

        with patch("sandbox.BUI_SANDBOXES_DIR", tmp_path / "sandboxes"):
            with patch("sandbox.Path.home", return_value=tmp_path):
                with patch("builtins.input", return_value="1"):
                    install_sandbox_binary(
                        "test",
                        profile="profile with spaces",
                    )

        script = (bin_dir / "myapp").read_text()
        assert "'profile with spaces'" in script

    def test_script_quotes_sandbox_name_with_metacharacters(self, tmp_path):
        """Sandbox names with shell metacharacters are properly quoted."""
        from sandbox import install_sandbox_binary

        sandbox_name = "test;id"
        sandbox_dir = tmp_path / "sandboxes" / sandbox_name
        overlays_dir = sandbox_dir / "overlays" / "home-sandbox" / "bin"
        overlays_dir.mkdir(parents=True)
        exe = overlays_dir / "myapp"
        exe.write_text("#!/bin/sh\necho hello")
        exe.chmod(0o755)

        bin_dir = tmp_path / ".local" / "bin"

        with patch("sandbox.BUI_SANDBOXES_DIR", tmp_path / "sandboxes"):
            with patch("sandbox.Path.home", return_value=tmp_path):
                with patch("builtins.input", return_value="1"):
                    install_sandbox_binary(sandbox_name, profile="untrusted")

        script = (bin_dir / "myapp").read_text()
        # Should be quoted to prevent command injection
        assert "'test;id'" in script
        # Should NOT have unquoted semicolon that could execute commands
        assert "--sandbox test;id" not in script

    def test_script_quotes_bind_paths_with_special_chars(self, tmp_path):
        """Bind paths with special characters are properly quoted."""
        from sandbox import install_sandbox_binary

        sandbox_dir = tmp_path / "sandboxes" / "test"
        overlays_dir = sandbox_dir / "overlays" / "home-sandbox" / "bin"
        overlays_dir.mkdir(parents=True)
        exe = overlays_dir / "myapp"
        exe.write_text("#!/bin/sh\necho hello")
        exe.chmod(0o755)

        bin_dir = tmp_path / ".local" / "bin"

        with patch("sandbox.BUI_SANDBOXES_DIR", tmp_path / "sandboxes"):
            with patch("sandbox.Path.home", return_value=tmp_path):
                with patch("builtins.input", return_value="1"):
                    install_sandbox_binary(
                        "test",
                        profile="untrusted",
                        bind_paths=["/path/with spaces", "/path/with$dollar"],
                    )

        script = (bin_dir / "myapp").read_text()
        assert "'/path/with spaces'" in script
        assert "'/path/with$dollar'" in script

    def test_script_quotes_bind_env_with_special_chars(self, tmp_path):
        """Bind env specs with special characters are properly quoted."""
        from sandbox import install_sandbox_binary

        sandbox_dir = tmp_path / "sandboxes" / "test"
        overlays_dir = sandbox_dir / "overlays" / "home-sandbox" / "bin"
        overlays_dir.mkdir(parents=True)
        exe = overlays_dir / "myapp"
        exe.write_text("#!/bin/sh\necho hello")
        exe.chmod(0o755)

        bin_dir = tmp_path / ".local" / "bin"

        with patch("sandbox.BUI_SANDBOXES_DIR", tmp_path / "sandboxes"):
            with patch("sandbox.Path.home", return_value=tmp_path):
                with patch("builtins.input", return_value="1"):
                    install_sandbox_binary(
                        "test",
                        profile="untrusted",
                        bind_env=["VAR=value'with'quotes"],
                    )

        script = (bin_dir / "myapp").read_text()
        # shlex.quote handles embedded quotes
        assert "VAR=value" in script
        # Should not have unquoted quotes that could break shell parsing
        assert "--bind-env VAR=value'with'quotes" not in script

    def test_script_prevents_command_injection(self, tmp_path):
        """Malicious input cannot inject shell commands."""
        from sandbox import install_sandbox_binary

        # Attempt command injection via sandbox name
        malicious_name = "test$(id>/tmp/pwned)"
        sandbox_dir = tmp_path / "sandboxes" / malicious_name
        overlays_dir = sandbox_dir / "overlays" / "home-sandbox" / "bin"
        overlays_dir.mkdir(parents=True)
        exe = overlays_dir / "myapp"
        exe.write_text("#!/bin/sh\necho hello")
        exe.chmod(0o755)

        bin_dir = tmp_path / ".local" / "bin"

        with patch("sandbox.BUI_SANDBOXES_DIR", tmp_path / "sandboxes"):
            with patch("sandbox.Path.home", return_value=tmp_path):
                with patch("builtins.input", return_value="1"):
                    install_sandbox_binary(malicious_name, profile="untrusted")

        script = (bin_dir / "myapp").read_text()
        # The $() should be quoted so it doesn't execute
        assert "'test$(id>/tmp/pwned)'" in script or '"test$(id>/tmp/pwned)"' in script
