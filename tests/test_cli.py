"""Tests for CLI argument parsing."""

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from cli import needs_shell_wrap, parse_args
from sandbox import (
    find_executables,
    install_sandbox_binary,
    list_overlays,
    list_profiles,
    list_sandboxes,
    register_sandbox,
    uninstall_sandbox,
)


class TestNeedsShellWrap:
    """Test needs_shell_wrap() function."""

    def test_simple_command_no_wrap(self):
        """Simple command doesn't need shell wrap."""
        assert needs_shell_wrap(["python", "script.py"]) is False

    def test_command_with_args_no_wrap(self):
        """Command with arguments doesn't need shell wrap."""
        assert needs_shell_wrap(["ls", "-la", "/home"]) is False

    def test_pipe_needs_wrap(self):
        """Command with pipe needs shell wrap."""
        assert needs_shell_wrap(["cat file.txt | grep error"]) is True

    def test_and_operator_needs_wrap(self):
        """Command with && needs shell wrap."""
        assert needs_shell_wrap(["cd /tmp && ls"]) is True

    def test_or_operator_needs_wrap(self):
        """Command with || needs shell wrap."""
        assert needs_shell_wrap(["test -f file || echo missing"]) is True

    def test_semicolon_needs_wrap(self):
        """Command with semicolon needs shell wrap."""
        assert needs_shell_wrap(["echo hello; echo world"]) is True

    def test_redirect_out_needs_wrap(self):
        """Command with > redirect needs shell wrap."""
        assert needs_shell_wrap(["echo hello > file.txt"]) is True

    def test_redirect_in_needs_wrap(self):
        """Command with < redirect needs shell wrap."""
        assert needs_shell_wrap(["cat < input.txt"]) is True

    def test_command_substitution_dollar_needs_wrap(self):
        """Command with $() substitution needs shell wrap."""
        assert needs_shell_wrap(["echo $(date)"]) is True

    def test_command_substitution_backtick_needs_wrap(self):
        """Command with backtick substitution needs shell wrap."""
        assert needs_shell_wrap(["echo `date`"]) is True

    def test_shell_char_in_any_arg(self):
        """Shell char in any argument triggers wrap."""
        # Shell char in middle argument
        assert needs_shell_wrap(["bash", "-c", "cmd1 | cmd2"]) is True

    def test_quoted_string_with_shell_char(self):
        """Shell char in quoted string still triggers wrap."""
        # The parsing happens before quoting evaluation
        assert needs_shell_wrap(['echo "hello | world"']) is True


class TestParseArgs:
    """Test parse_args() function."""

    def test_command_after_separator(self):
        """Command after -- is parsed correctly."""
        with patch.object(sys, "argv", ["bui", "--", "bash"]):
            args = parse_args()
            assert args.command == ["bash"]
            assert args.profile_path is None
            assert args.sandbox_name is None
            assert args.bind_cwd is False
            assert args.bind_paths == []

    def test_command_with_args(self):
        """Command with arguments after --."""
        with patch.object(sys, "argv", ["bui", "--", "python", "script.py", "-v"]):
            args = parse_args()
            assert args.command == ["python", "script.py", "-v"]

    def test_profile_flag(self):
        """--profile flag is parsed."""
        with patch.object(
            sys, "argv", ["bui", "--profile", "test.json", "--", "bash"]
        ):
            args = parse_args()
            assert args.command == ["bash"]
            assert args.profile_path == "test.json"

    def test_profile_flag_path(self):
        """--profile with full path."""
        with patch.object(
            sys, "argv", ["bui", "--profile", "/home/user/profiles/dev.json", "--", "bash"]
        ):
            args = parse_args()
            assert args.profile_path == "/home/user/profiles/dev.json"

    def test_no_separator(self):
        """Command without -- separator."""
        with patch.object(sys, "argv", ["bui", "bash"]):
            args = parse_args()
            assert args.command == ["bash"]

    def test_shell_wrap_applied(self):
        """Shell metacharacters trigger shell wrap."""
        with patch.object(sys, "argv", ["bui", "--", "cat foo | grep bar"]):
            args = parse_args()
            # shlex.join quotes the argument
            assert args.command[0] == "/bin/bash"
            assert args.command[1] == "-c"
            assert "cat foo | grep bar" in args.command[2]

    def test_sandbox_flag(self):
        """--sandbox flag is parsed."""
        with patch.object(
            sys, "argv", ["bui", "--profile", "untrusted", "--sandbox", "test", "--", "bash"]
        ):
            args = parse_args()
            assert args.command == ["bash"]
            assert args.profile_path == "untrusted"
            assert args.sandbox_name == "test"

    def test_bind_cwd_flag(self):
        """--bind-cwd flag is parsed."""
        with patch.object(
            sys, "argv", ["bui", "--profile", "untrusted", "--bind-cwd", "--", "bash"]
        ):
            args = parse_args()
            assert args.command == ["bash"]
            assert args.bind_cwd is True

    def test_bind_cwd_with_sandbox(self):
        """--bind-cwd with --sandbox."""
        with patch.object(
            sys, "argv", ["bui", "--profile", "untrusted", "--sandbox", "test", "--bind-cwd", "--", "bash"]
        ):
            args = parse_args()
            assert args.sandbox_name == "test"
            assert args.bind_cwd is True

    def test_single_bind_path(self):
        """Single --bind path is parsed and resolved."""
        with patch.object(
            sys, "argv", ["bui", "--profile", "untrusted", "--bind", "/tmp/test", "--", "bash"]
        ):
            args = parse_args()
            assert args.command == ["bash"]
            assert len(args.bind_paths) == 1
            assert args.bind_paths[0] == Path("/tmp/test")

    def test_multiple_bind_paths(self):
        """Multiple --bind paths are parsed."""
        with patch.object(
            sys, "argv", ["bui", "--profile", "untrusted", "--bind", "/tmp/a", "--bind", "/tmp/b", "--", "bash"]
        ):
            args = parse_args()
            assert len(args.bind_paths) == 2
            assert args.bind_paths[0] == Path("/tmp/a")
            assert args.bind_paths[1] == Path("/tmp/b")

    def test_bind_path_expansion(self, tmp_path):
        """--bind expands ~ in paths."""
        with patch.object(
            sys, "argv", ["bui", "--profile", "untrusted", "--bind", "~/.nvm", "--", "bash"]
        ):
            args = parse_args()
            assert len(args.bind_paths) == 1
            # Path should be expanded (not contain ~)
            assert "~" not in str(args.bind_paths[0])
            assert args.bind_paths[0].is_absolute()

    def test_bind_with_bind_cwd(self):
        """--bind can be combined with --bind-cwd."""
        with patch.object(
            sys, "argv", ["bui", "--profile", "untrusted", "--bind", "/tmp/test", "--bind-cwd", "--", "bash"]
        ):
            args = parse_args()
            assert args.bind_cwd is True
            assert len(args.bind_paths) == 1
            assert args.bind_paths[0] == Path("/tmp/test")

    def test_bind_with_sandbox(self):
        """--bind can be combined with --sandbox."""
        with patch.object(
            sys, "argv", ["bui", "--profile", "untrusted", "--sandbox", "test", "--bind", "/tmp/tools", "--", "bash"]
        ):
            args = parse_args()
            assert args.sandbox_name == "test"
            assert len(args.bind_paths) == 1
            assert args.bind_paths[0] == Path("/tmp/tools")

    def test_help_flag_exits(self):
        """--help flag shows help and exits."""
        with patch.object(sys, "argv", ["bui", "--help"]):
            with pytest.raises(SystemExit):
                parse_args()

    def test_h_flag_exits(self):
        """-h flag shows help and exits."""
        with patch.object(sys, "argv", ["bui", "-h"]):
            with pytest.raises(SystemExit):
                parse_args()

    def test_no_args_shows_help(self):
        """No arguments shows help."""
        with patch.object(sys, "argv", ["bui"]):
            with pytest.raises(SystemExit):
                parse_args()

    def test_empty_command_after_separator_exits(self):
        """Empty command after -- exits with error."""
        with patch.object(sys, "argv", ["bui", "--"]):
            with pytest.raises(SystemExit):
                parse_args()

    def test_profile_without_path_exits(self):
        """--profile without path exits with error."""
        with patch.object(sys, "argv", ["bui", "--profile", "--", "bash"]):
            with pytest.raises(SystemExit):
                parse_args()

    def test_install_flag_exits(self):
        """--install flag exits."""
        with patch.object(sys, "argv", ["bui", "--install"]):
            with patch("cli.do_install"):
                with pytest.raises(SystemExit):
                    parse_args()

    def test_update_flag_exits(self):
        """--update flag exits."""
        with patch.object(sys, "argv", ["bui", "--update"]):
            with patch("cli.do_update"):
                with pytest.raises(SystemExit):
                    parse_args()

    def test_install_with_sandbox_calls_install_sandbox_binary(self):
        """--install with --sandbox calls install_sandbox_binary."""
        with patch.object(sys, "argv", ["bui", "--sandbox", "test", "--install"]):
            with patch("cli.install_sandbox_binary") as mock_install:
                mock_install.side_effect = SystemExit(0)
                with pytest.raises(SystemExit):
                    parse_args()
                mock_install.assert_called_once_with("test", "untrusted", None, None)

    def test_install_without_sandbox_installs_bui(self):
        """--install without --sandbox installs bui itself."""
        with patch.object(sys, "argv", ["bui", "--install"]):
            with patch("cli.do_install") as mock_do_install:
                with pytest.raises(SystemExit):
                    parse_args()
                mock_do_install.assert_called_once()

    def test_uninstall_with_sandbox_exits(self):
        """--uninstall with --sandbox calls uninstall_sandbox and exits."""
        with patch.object(sys, "argv", ["bui", "--sandbox", "test", "--uninstall"]):
            with patch("cli.uninstall_sandbox") as mock_uninstall:
                mock_uninstall.side_effect = SystemExit(0)
                with pytest.raises(SystemExit):
                    parse_args()
                mock_uninstall.assert_called_once_with("test")

    def test_uninstall_requires_sandbox(self):
        """--uninstall requires --sandbox."""
        with patch.object(sys, "argv", ["bui", "--uninstall"]):
            with pytest.raises(SystemExit):
                parse_args()

    def test_list_sandboxes_exits(self):
        """--list-sandboxes calls list_sandboxes and exits."""
        with patch.object(sys, "argv", ["bui", "--list-sandboxes"]):
            with patch("cli.list_sandboxes") as mock_list:
                with pytest.raises(SystemExit):
                    parse_args()
                mock_list.assert_called_once()


class TestFindExecutables:
    """Test find_executables() function."""

    def test_finds_executable_files(self, tmp_path):
        """Finds executable files in directory."""
        # Create an executable file
        exe = tmp_path / "bin" / "myapp"
        exe.parent.mkdir()
        exe.write_text("#!/bin/bash\necho hello")
        exe.chmod(0o755)

        # Create a non-executable file
        txt = tmp_path / "readme.txt"
        txt.write_text("readme")

        result = find_executables(tmp_path)
        assert len(result) == 1
        assert result[0] == exe

    def test_excludes_cache_directories(self, tmp_path):
        """Excludes files in cache directories."""
        # Create executable in cache dir
        cache_exe = tmp_path / ".cache" / "something" / "bin"
        cache_exe.parent.mkdir(parents=True)
        cache_exe.write_text("#!/bin/bash")
        cache_exe.chmod(0o755)

        # Create executable in .local/share
        share_exe = tmp_path / ".local" / "share" / "app" / "bin"
        share_exe.parent.mkdir(parents=True)
        share_exe.write_text("#!/bin/bash")
        share_exe.chmod(0o755)

        # Create regular executable
        regular_exe = tmp_path / "bin" / "app"
        regular_exe.parent.mkdir()
        regular_exe.write_text("#!/bin/bash")
        regular_exe.chmod(0o755)

        result = find_executables(tmp_path)
        assert len(result) == 1
        assert result[0] == regular_exe

    def test_returns_sorted_list(self, tmp_path):
        """Returns executables sorted by path."""
        for name in ["zebra", "alpha", "beta"]:
            exe = tmp_path / name
            exe.write_text("#!/bin/bash")
            exe.chmod(0o755)

        result = find_executables(tmp_path)
        names = [p.name for p in result]
        assert names == ["alpha", "beta", "zebra"]


class TestInstallSandboxBinary:
    """Test install_sandbox_binary() function."""

    def test_sandbox_not_found_exits(self, tmp_path):
        """Exits with error if sandbox directory doesn't exist."""
        with patch("sandbox.BUI_STATE_DIR", tmp_path / ".local" / "state" / "bui"):
            with pytest.raises(SystemExit):
                install_sandbox_binary("nonexistent")

    def test_no_executables_exits(self, tmp_path):
        """Exits with error if no executables found."""
        state_dir = tmp_path / ".local" / "state" / "bui"
        overlay_dir = state_dir / "overlays" / "test"
        overlay_dir.mkdir(parents=True)
        # Create a non-executable file
        (overlay_dir / "readme.txt").write_text("readme")

        with patch("sandbox.BUI_STATE_DIR", state_dir):
            with pytest.raises(SystemExit):
                install_sandbox_binary("test")

    def test_installs_script(self, tmp_path, capsys):
        """Installs script for selected executable."""
        state_dir = tmp_path / ".local" / "state" / "bui"
        overlay_dir = state_dir / "overlays" / "deno"
        overlay_dir.mkdir(parents=True)
        bin_dir = tmp_path / ".local" / "bin"
        installed_file = state_dir / "installed.json"

        # Create executable
        exe = overlay_dir / ".deno" / "bin" / "deno"
        exe.parent.mkdir(parents=True)
        exe.write_text("#!/bin/bash")
        exe.chmod(0o755)

        with patch("sandbox.BUI_STATE_DIR", state_dir):
            with patch("sandbox.INSTALLED_SCRIPTS_FILE", installed_file):
                with patch("sandbox.Path.home", return_value=tmp_path):
                    with patch("builtins.input", return_value="1"):
                        install_sandbox_binary("deno")

        captured = capsys.readouterr()
        assert "Executables in sandbox 'deno':" in captured.out
        assert ".deno/bin/deno" in captured.out
        assert f"Installed: {bin_dir / 'deno'}" in captured.out

        # Verify script was created
        script_path = bin_dir / "deno"
        assert script_path.exists()
        content = script_path.read_text()
        assert "#!/bin/sh" in content
        assert "--sandbox deno" in content
        assert "--bind-cwd" in content
        # Path should be sandbox home, not host home
        assert "/home/sandbox/.deno/bin/deno" in content
        assert "~/.deno/bin/deno" not in content
        assert script_path.stat().st_mode & 0o755

        # Verify metadata was saved
        import json
        metadata = json.loads(installed_file.read_text())
        assert "deno" in metadata
        assert "deno" in metadata["deno"]["scripts"]
        assert metadata["deno"]["profile"] == "untrusted"

    def test_installs_script_with_binds(self, tmp_path, capsys):
        """Installs script with --bind and --bind-env flags."""
        state_dir = tmp_path / ".local" / "state" / "bui"
        overlay_dir = state_dir / "overlays" / "myapp"
        overlay_dir.mkdir(parents=True)
        bin_dir = tmp_path / ".local" / "bin"
        installed_file = state_dir / "installed.json"

        # Create executable
        exe = overlay_dir / "bin" / "myapp"
        exe.parent.mkdir(parents=True)
        exe.write_text("#!/bin/bash")
        exe.chmod(0o755)

        with patch("sandbox.BUI_STATE_DIR", state_dir):
            with patch("sandbox.INSTALLED_SCRIPTS_FILE", installed_file):
                with patch("sandbox.Path.home", return_value=tmp_path):
                    with patch("builtins.input", return_value="1"):
                        install_sandbox_binary(
                            "myapp",
                            profile="untrusted",
                            bind_paths=["/usr/bin", "/opt/tools"],
                            bind_env=["FOO=bar", "BAZ=qux"],
                        )

        # Verify script has bind flags
        script_path = bin_dir / "myapp"
        content = script_path.read_text()
        assert "--bind /usr/bin" in content
        assert "--bind /opt/tools" in content
        assert "--bind-env 'FOO=bar'" in content
        assert "--bind-env 'BAZ=qux'" in content

        # Verify metadata has binds
        import json
        metadata = json.loads(installed_file.read_text())
        assert metadata["myapp"]["bind_paths"] == ["/usr/bin", "/opt/tools"]
        assert metadata["myapp"]["bind_env"] == ["FOO=bar", "BAZ=qux"]

    def test_reads_binds_from_metadata(self, tmp_path, capsys):
        """Reads bind paths and env from existing metadata if not provided."""
        state_dir = tmp_path / ".local" / "state" / "bui"
        overlay_dir = state_dir / "overlays" / "cached"
        overlay_dir.mkdir(parents=True)
        bin_dir = tmp_path / ".local" / "bin"
        installed_file = state_dir / "installed.json"

        # Pre-populate metadata (as if register_sandbox was called earlier)
        import json
        installed_file.parent.mkdir(parents=True, exist_ok=True)
        installed_file.write_text(json.dumps({
            "cached": {
                "scripts": [],
                "profile": "myprofile",
                "bind_paths": ["/pre/bound"],
                "bind_env": ["CACHED=value"],
            }
        }))

        # Create executable
        exe = overlay_dir / "app"
        exe.write_text("#!/bin/bash")
        exe.chmod(0o755)

        with patch("sandbox.BUI_STATE_DIR", state_dir):
            with patch("sandbox.INSTALLED_SCRIPTS_FILE", installed_file):
                with patch("sandbox.Path.home", return_value=tmp_path):
                    with patch("builtins.input", return_value="1"):
                        # Don't pass bind_paths or bind_env - should read from metadata
                        install_sandbox_binary("cached")

        # Verify script uses metadata values
        script_path = bin_dir / "app"
        content = script_path.read_text()
        assert "--profile myprofile" in content
        assert "--bind /pre/bound" in content
        assert "--bind-env 'CACHED=value'" in content

    def test_invalid_selection_exits(self, tmp_path):
        """Exits with error on invalid selection."""
        state_dir = tmp_path / ".local" / "state" / "bui"
        overlay_dir = state_dir / "overlays" / "test"
        overlay_dir.mkdir(parents=True)

        exe = overlay_dir / "bin" / "app"
        exe.parent.mkdir()
        exe.write_text("#!/bin/bash")
        exe.chmod(0o755)

        with patch("sandbox.BUI_STATE_DIR", state_dir):
            with patch("sandbox.Path.home", return_value=tmp_path):
                with patch("builtins.input", return_value="invalid"):
                    with pytest.raises(SystemExit):
                        install_sandbox_binary("test")

    def test_out_of_range_selection_exits(self, tmp_path):
        """Exits with error on out of range selection."""
        state_dir = tmp_path / ".local" / "state" / "bui"
        overlay_dir = state_dir / "overlays" / "test"
        overlay_dir.mkdir(parents=True)

        exe = overlay_dir / "bin" / "app"
        exe.parent.mkdir()
        exe.write_text("#!/bin/bash")
        exe.chmod(0o755)

        with patch("sandbox.BUI_STATE_DIR", state_dir):
            with patch("sandbox.Path.home", return_value=tmp_path):
                with patch("builtins.input", return_value="99"):
                    with pytest.raises(SystemExit):
                        install_sandbox_binary("test")

    def test_eof_exits(self, tmp_path):
        """Exits with error on EOF (e.g., piped input)."""
        state_dir = tmp_path / ".local" / "state" / "bui"
        overlay_dir = state_dir / "overlays" / "test"
        overlay_dir.mkdir(parents=True)

        exe = overlay_dir / "bin" / "app"
        exe.parent.mkdir()
        exe.write_text("#!/bin/bash")
        exe.chmod(0o755)

        with patch("sandbox.BUI_STATE_DIR", state_dir):
            with patch("sandbox.Path.home", return_value=tmp_path):
                with patch("builtins.input", side_effect=EOFError):
                    with pytest.raises(SystemExit):
                        install_sandbox_binary("test")

    def test_multiple_executables_select_second(self, tmp_path, capsys):
        """Can select from multiple executables."""
        state_dir = tmp_path / ".local" / "state" / "bui"
        overlay_dir = state_dir / "overlays" / "multi"
        overlay_dir.mkdir(parents=True)
        bin_dir = tmp_path / ".local" / "bin"
        installed_file = state_dir / "installed.json"

        # Create two executables
        for name in ["alpha", "beta"]:
            exe = overlay_dir / "bin" / name
            exe.parent.mkdir(exist_ok=True)
            exe.write_text("#!/bin/bash")
            exe.chmod(0o755)

        with patch("sandbox.BUI_STATE_DIR", state_dir):
            with patch("sandbox.INSTALLED_SCRIPTS_FILE", installed_file):
                with patch("sandbox.Path.home", return_value=tmp_path):
                    with patch("builtins.input", return_value="2"):
                        install_sandbox_binary("multi")

        captured = capsys.readouterr()
        assert "1. bin/alpha" in captured.out
        assert "2. bin/beta" in captured.out
        assert f"Installed: {bin_dir / 'beta'}" in captured.out

        # Verify correct script was created
        assert (bin_dir / "beta").exists()
        assert not (bin_dir / "alpha").exists()


class TestRegisterSandbox:
    """Test register_sandbox() function."""

    def test_registers_new_sandbox(self, tmp_path):
        """Registers a new sandbox with metadata."""
        state_dir = tmp_path / ".local" / "state" / "bui"
        installed_file = state_dir / "installed.json"

        with patch("sandbox.INSTALLED_SCRIPTS_FILE", installed_file):
            register_sandbox("mysandbox", "untrusted")

        import json
        metadata = json.loads(installed_file.read_text())
        assert "mysandbox" in metadata
        assert metadata["mysandbox"]["profile"] == "untrusted"
        assert metadata["mysandbox"]["scripts"] == []

    def test_registers_with_binds(self, tmp_path):
        """Registers sandbox with bind_paths and bind_env."""
        state_dir = tmp_path / ".local" / "state" / "bui"
        installed_file = state_dir / "installed.json"

        with patch("sandbox.INSTALLED_SCRIPTS_FILE", installed_file):
            register_sandbox(
                "myapp",
                "custom-profile",
                bind_paths=["/usr/bin", "/opt"],
                bind_env=["FOO=bar", "BAZ=123"],
            )

        import json
        metadata = json.loads(installed_file.read_text())
        assert metadata["myapp"]["profile"] == "custom-profile"
        assert metadata["myapp"]["bind_paths"] == ["/usr/bin", "/opt"]
        assert metadata["myapp"]["bind_env"] == ["FOO=bar", "BAZ=123"]

    def test_does_not_overwrite_existing(self, tmp_path):
        """Does not overwrite existing sandbox metadata."""
        state_dir = tmp_path / ".local" / "state" / "bui"
        installed_file = state_dir / "installed.json"

        # Pre-populate with existing sandbox
        import json
        installed_file.parent.mkdir(parents=True, exist_ok=True)
        installed_file.write_text(json.dumps({
            "existing": {
                "scripts": ["mybin"],
                "profile": "old-profile",
                "bind_paths": ["/old/path"],
            }
        }))

        with patch("sandbox.INSTALLED_SCRIPTS_FILE", installed_file):
            # Try to register same sandbox with different values
            register_sandbox(
                "existing",
                "new-profile",
                bind_paths=["/new/path"],
            )

        # Should keep original values
        metadata = json.loads(installed_file.read_text())
        assert metadata["existing"]["profile"] == "old-profile"
        assert metadata["existing"]["bind_paths"] == ["/old/path"]
        assert metadata["existing"]["scripts"] == ["mybin"]


class TestFindExecutablesEdgeCases:
    """Additional edge case tests for find_executables()."""

    def test_excludes_npm_directory(self, tmp_path):
        """Excludes files in .npm/ directory."""
        npm_exe = tmp_path / ".npm" / "_npx" / "bin"
        npm_exe.parent.mkdir(parents=True)
        npm_exe.write_text("#!/bin/bash")
        npm_exe.chmod(0o755)

        result = find_executables(tmp_path)
        assert len(result) == 0

    def test_excludes_cargo_registry(self, tmp_path):
        """Excludes files in .cargo/registry/ directory."""
        cargo_exe = tmp_path / ".cargo" / "registry" / "bin" / "tool"
        cargo_exe.parent.mkdir(parents=True)
        cargo_exe.write_text("#!/bin/bash")
        cargo_exe.chmod(0o755)

        result = find_executables(tmp_path)
        assert len(result) == 0

    def test_includes_cargo_bin(self, tmp_path):
        """Includes files in .cargo/bin/ (not registry)."""
        cargo_exe = tmp_path / ".cargo" / "bin" / "rustc"
        cargo_exe.parent.mkdir(parents=True)
        cargo_exe.write_text("#!/bin/bash")
        cargo_exe.chmod(0o755)

        result = find_executables(tmp_path)
        assert len(result) == 1
        assert result[0].name == "rustc"

    def test_empty_directory(self, tmp_path):
        """Returns empty list for empty directory."""
        result = find_executables(tmp_path)
        assert result == []

    def test_only_non_executable_files(self, tmp_path):
        """Returns empty list when no files are executable."""
        txt = tmp_path / "readme.txt"
        txt.write_text("hello")

        script = tmp_path / "script.sh"
        script.write_text("#!/bin/bash")
        # Not chmod +x

        result = find_executables(tmp_path)
        assert result == []


class TestUninstallSandbox:
    """Test uninstall_sandbox() function."""

    def test_sandbox_not_found_exits(self, tmp_path):
        """Exits with error if neither overlay dir nor metadata exist."""
        state_dir = tmp_path / ".local" / "state" / "bui"
        state_dir.mkdir(parents=True)
        installed_file = state_dir / "installed.json"
        installed_file.write_text("{}")

        with patch("sandbox.BUI_STATE_DIR", state_dir):
            with patch("sandbox.INSTALLED_SCRIPTS_FILE", installed_file):
                with pytest.raises(SystemExit):
                    uninstall_sandbox("nonexistent")

    def test_metadata_only_cleans_up(self, tmp_path, capsys):
        """Cleans up metadata even when overlay was already deleted."""
        state_dir = tmp_path / ".local" / "state" / "bui"
        state_dir.mkdir(parents=True)
        bin_dir = tmp_path / ".local" / "bin"
        bin_dir.mkdir(parents=True)
        installed_file = state_dir / "installed.json"

        # Metadata exists but overlay doesn't
        installed_file.write_text('{"orphan": {"scripts": ["myapp"], "profile": "untrusted"}}')

        # Create the script that was installed
        script = bin_dir / "myapp"
        script.write_text("#!/bin/sh\nexec bui --sandbox orphan -- ~/bin/myapp\n")

        with patch("sandbox.BUI_STATE_DIR", state_dir):
            with patch("sandbox.INSTALLED_SCRIPTS_FILE", installed_file):
                with patch("sandbox.Path.home", return_value=tmp_path):
                    uninstall_sandbox("orphan")

        captured = capsys.readouterr()
        assert f"Removed: {bin_dir / 'myapp'}" in captured.out
        # Should NOT say "Removed: overlay_dir" since it didn't exist
        assert "overlays/orphan" not in captured.out

        # Verify script was removed
        assert not script.exists()
        # Verify metadata was cleaned up
        import json
        metadata = json.loads(installed_file.read_text())
        assert "orphan" not in metadata

    def test_removes_scripts_and_overlay(self, tmp_path, capsys):
        """Removes installed scripts and overlay directory."""
        state_dir = tmp_path / ".local" / "state" / "bui"
        overlay_dir = state_dir / "overlays" / "test"
        overlay_dir.mkdir(parents=True)
        bin_dir = tmp_path / ".local" / "bin"
        bin_dir.mkdir(parents=True)
        installed_file = state_dir / "installed.json"

        # Create sandbox data
        (overlay_dir / "some_file").write_text("data")

        # Create wrapper script
        script = bin_dir / "myapp"
        script.write_text("#!/bin/sh\nexec bui --profile untrusted --sandbox test --bind-cwd -- ~/bin/myapp\n")

        # Create metadata tracking the installed script
        installed_file.write_text('{"test": {"scripts": ["myapp"], "profile": "untrusted"}}')

        # Create unrelated script (should not be removed)
        other_script = bin_dir / "other"
        other_script.write_text("#!/bin/sh\necho hello\n")

        with patch("sandbox.BUI_STATE_DIR", state_dir):
            with patch("sandbox.INSTALLED_SCRIPTS_FILE", installed_file):
                with patch("sandbox.Path.home", return_value=tmp_path):
                    uninstall_sandbox("test")

        captured = capsys.readouterr()
        assert f"Removed: {bin_dir / 'myapp'}" in captured.out
        assert f"Removed: {overlay_dir}/" in captured.out

        # Verify script was removed
        assert not script.exists()
        # Verify unrelated script still exists
        assert other_script.exists()
        # Verify overlay was removed
        assert not overlay_dir.exists()

    def test_no_scripts_just_removes_overlay(self, tmp_path, capsys):
        """Works when no scripts are installed."""
        state_dir = tmp_path / ".local" / "state" / "bui"
        overlay_dir = state_dir / "overlays" / "test"
        overlay_dir.mkdir(parents=True)
        installed_file = state_dir / "installed.json"
        installed_file.write_text("{}")

        (overlay_dir / "data").write_text("test")

        with patch("sandbox.BUI_STATE_DIR", state_dir):
            with patch("sandbox.INSTALLED_SCRIPTS_FILE", installed_file):
                with patch("sandbox.Path.home", return_value=tmp_path):
                    uninstall_sandbox("test")

        captured = capsys.readouterr()
        assert f"Removed: {overlay_dir}/" in captured.out
        assert not overlay_dir.exists()


class TestListSandboxes:
    """Test list_sandboxes() function - lists from metadata only."""

    def test_no_metadata_file(self, tmp_path, capsys):
        """Shows message when no metadata file exists."""
        state_dir = tmp_path / ".local" / "state" / "bui"
        installed_file = state_dir / "installed.json"
        # Don't create the file

        with patch("sandbox.INSTALLED_SCRIPTS_FILE", installed_file):
            list_sandboxes()

        captured = capsys.readouterr()
        assert "No sandboxes installed" in captured.out
        assert "--list-overlays" in captured.out

    def test_empty_metadata(self, tmp_path, capsys):
        """Shows message when metadata is empty."""
        state_dir = tmp_path / ".local" / "state" / "bui"
        state_dir.mkdir(parents=True)
        installed_file = state_dir / "installed.json"
        installed_file.write_text("{}")

        with patch("sandbox.INSTALLED_SCRIPTS_FILE", installed_file):
            list_sandboxes()

        captured = capsys.readouterr()
        assert "No sandboxes installed" in captured.out
        assert "--list-overlays" in captured.out

    def test_lists_sandboxes_with_scripts(self, tmp_path, capsys):
        """Lists sandboxes with their installed scripts and profiles."""
        state_dir = tmp_path / ".local" / "state" / "bui"
        state_dir.mkdir(parents=True)
        installed_file = state_dir / "installed.json"

        # Create metadata for installed scripts
        installed_file.write_text('{"deno": {"scripts": ["deno"], "profile": "untrusted"}, "node": {"scripts": ["node", "npm"], "profile": "custom"}}')

        with patch("sandbox.INSTALLED_SCRIPTS_FILE", installed_file):
            list_sandboxes()

        captured = capsys.readouterr()
        assert "Sandboxes:" in captured.out
        assert "deno" in captured.out
        assert "profile: untrusted" in captured.out
        assert "scripts: deno" in captured.out
        assert "node" in captured.out
        assert "profile: custom" in captured.out
        assert "scripts: node, npm" in captured.out


class TestListOverlays:
    """Test list_overlays() function - lists overlay directories."""

    def test_no_overlays_dir(self, tmp_path, capsys):
        """Shows message when no overlays directory exists."""
        state_dir = tmp_path / ".local" / "state" / "bui"
        # Don't create the directory

        with patch("sandbox.BUI_STATE_DIR", state_dir):
            list_overlays()

        captured = capsys.readouterr()
        assert "No overlays found" in captured.out

    def test_empty_overlays_dir(self, tmp_path, capsys):
        """Shows message when overlays directory is empty."""
        state_dir = tmp_path / ".local" / "state" / "bui"
        overlays_dir = state_dir / "overlays"
        overlays_dir.mkdir(parents=True)

        with patch("sandbox.BUI_STATE_DIR", state_dir):
            list_overlays()

        captured = capsys.readouterr()
        assert "No overlays found" in captured.out

    def test_lists_overlays_with_file_count(self, tmp_path, capsys):
        """Lists overlays with file counts."""
        state_dir = tmp_path / ".local" / "state" / "bui"
        overlays_dir = state_dir / "overlays"
        deno_dir = overlays_dir / "deno"
        deno_dir.mkdir(parents=True)
        # Create some files
        (deno_dir / "file1.txt").write_text("test")
        (deno_dir / "file2.txt").write_text("test")
        subdir = deno_dir / "subdir"
        subdir.mkdir()
        (subdir / "file3.txt").write_text("test")

        installed_file = state_dir / "installed.json"
        installed_file.write_text("{}")

        with patch("sandbox.BUI_STATE_DIR", state_dir):
            with patch("sandbox.INSTALLED_SCRIPTS_FILE", installed_file):
                list_overlays()

        captured = capsys.readouterr()
        assert "Overlays:" in captured.out
        assert "deno" in captured.out
        assert "files: 3" in captured.out
        assert "safe to delete" in captured.out

    def test_shows_sandbox_status(self, tmp_path, capsys):
        """Shows whether overlay has associated sandbox."""
        state_dir = tmp_path / ".local" / "state" / "bui"
        overlays_dir = state_dir / "overlays"
        (overlays_dir / "deno").mkdir(parents=True)
        (overlays_dir / "orphan").mkdir(parents=True)

        installed_file = state_dir / "installed.json"
        installed_file.write_text('{"deno": {"scripts": ["deno"], "profile": "untrusted"}}')

        with patch("sandbox.BUI_STATE_DIR", state_dir):
            with patch("sandbox.INSTALLED_SCRIPTS_FILE", installed_file):
                list_overlays()

        captured = capsys.readouterr()
        assert "deno" in captured.out
        assert "bui --sandbox deno --uninstall" in captured.out
        assert "orphan" in captured.out
        assert "safe to delete" in captured.out

    def test_excludes_hidden_directories(self, tmp_path, capsys):
        """Excludes hidden directories from overlay list."""
        state_dir = tmp_path / ".local" / "state" / "bui"
        overlays_dir = state_dir / "overlays"
        (overlays_dir / "deno").mkdir(parents=True)
        (overlays_dir / ".hidden").mkdir(parents=True)
        installed_file = state_dir / "installed.json"
        installed_file.write_text("{}")

        with patch("sandbox.BUI_STATE_DIR", state_dir):
            with patch("sandbox.INSTALLED_SCRIPTS_FILE", installed_file):
                list_overlays()

        captured = capsys.readouterr()
        assert "deno" in captured.out
        assert ".hidden" not in captured.out


class TestListProfiles:
    """Test list_profiles() function."""

    def test_no_profiles_dir(self, tmp_path, capsys):
        """Shows message when no profiles directory exists."""
        profiles_dir = tmp_path / ".config" / "bui" / "profiles"
        # Don't create the directory

        with patch("sandbox.BUI_PROFILES_DIR", profiles_dir):
            list_profiles()

        captured = capsys.readouterr()
        assert "No profiles found" in captured.out

    def test_empty_profiles_dir(self, tmp_path, capsys):
        """Shows message when profiles directory is empty."""
        profiles_dir = tmp_path / ".config" / "bui" / "profiles"
        profiles_dir.mkdir(parents=True)

        with patch("sandbox.BUI_PROFILES_DIR", profiles_dir):
            list_profiles()

        captured = capsys.readouterr()
        assert "No profiles found" in captured.out

    def test_lists_profiles(self, tmp_path, capsys):
        """Lists available profiles."""
        profiles_dir = tmp_path / ".config" / "bui" / "profiles"
        profiles_dir.mkdir(parents=True)

        # Create some profile files
        (profiles_dir / "untrusted.json").write_text("{}")
        (profiles_dir / "dev.json").write_text("{}")

        with patch("sandbox.BUI_PROFILES_DIR", profiles_dir):
            list_profiles()

        captured = capsys.readouterr()
        assert "Profiles:" in captured.out
        assert "untrusted" in captured.out
        assert "dev" in captured.out
        assert "Profile directory:" in captured.out

    def test_list_profiles_exits(self):
        """--list-profiles flag exits."""
        with patch.object(sys, "argv", ["bui", "--list-profiles"]):
            with patch("cli.list_profiles") as mock_list:
                with pytest.raises(SystemExit):
                    parse_args()
                mock_list.assert_called_once()
