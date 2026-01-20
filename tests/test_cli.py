"""Tests for CLI argument parsing."""

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from cli import find_executables, generate_sandbox_alias, needs_shell_wrap, parse_args


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
            command, profile, sandbox, bind_cwd = parse_args()
            assert command == ["bash"]
            assert profile is None
            assert sandbox is None
            assert bind_cwd is False

    def test_command_with_args(self):
        """Command with arguments after --."""
        with patch.object(sys, "argv", ["bui", "--", "python", "script.py", "-v"]):
            command, profile, sandbox, bind_cwd = parse_args()
            assert command == ["python", "script.py", "-v"]

    def test_profile_flag(self):
        """--profile flag is parsed."""
        with patch.object(
            sys, "argv", ["bui", "--profile", "test.json", "--", "bash"]
        ):
            command, profile, sandbox, bind_cwd = parse_args()
            assert command == ["bash"]
            assert profile == "test.json"

    def test_profile_flag_path(self):
        """--profile with full path."""
        with patch.object(
            sys, "argv", ["bui", "--profile", "/home/user/profiles/dev.json", "--", "bash"]
        ):
            command, profile, sandbox, bind_cwd = parse_args()
            assert profile == "/home/user/profiles/dev.json"

    def test_no_separator(self):
        """Command without -- separator."""
        with patch.object(sys, "argv", ["bui", "bash"]):
            command, profile, sandbox, bind_cwd = parse_args()
            assert command == ["bash"]

    def test_shell_wrap_applied(self):
        """Shell metacharacters trigger shell wrap."""
        with patch.object(sys, "argv", ["bui", "--", "cat foo | grep bar"]):
            command, profile, sandbox, bind_cwd = parse_args()
            # shlex.join quotes the argument
            assert command[0] == "/bin/bash"
            assert command[1] == "-c"
            assert "cat foo | grep bar" in command[2]

    def test_sandbox_flag(self):
        """--sandbox flag is parsed."""
        with patch.object(
            sys, "argv", ["bui", "--profile", "untrusted", "--sandbox", "test", "--", "bash"]
        ):
            command, profile, sandbox, bind_cwd = parse_args()
            assert command == ["bash"]
            assert profile == "untrusted"
            assert sandbox == "test"

    def test_bind_cwd_flag(self):
        """--bind-cwd flag is parsed."""
        with patch.object(
            sys, "argv", ["bui", "--profile", "untrusted", "--bind-cwd", "--", "bash"]
        ):
            command, profile, sandbox, bind_cwd = parse_args()
            assert command == ["bash"]
            assert bind_cwd is True

    def test_bind_cwd_with_sandbox(self):
        """--bind-cwd with --sandbox."""
        with patch.object(
            sys, "argv", ["bui", "--profile", "untrusted", "--sandbox", "test", "--bind-cwd", "--", "bash"]
        ):
            command, profile, sandbox, bind_cwd = parse_args()
            assert sandbox == "test"
            assert bind_cwd is True

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

    def test_generate_without_sandbox_exits(self):
        """--generate without --sandbox exits with error."""
        with patch.object(sys, "argv", ["bui", "--generate"]):
            with pytest.raises(SystemExit):
                parse_args()

    def test_generate_with_sandbox_exits(self):
        """--generate with --sandbox calls generate_sandbox_alias and exits."""
        with patch.object(sys, "argv", ["bui", "--sandbox", "test", "--generate"]):
            with patch("cli.generate_sandbox_alias") as mock_gen:
                mock_gen.side_effect = SystemExit(0)
                with pytest.raises(SystemExit):
                    parse_args()
                mock_gen.assert_called_once_with("test")


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


class TestGenerateSandboxAlias:
    """Test generate_sandbox_alias() function."""

    def test_sandbox_not_found_exits(self, tmp_path):
        """Exits with error if sandbox directory doesn't exist."""
        with patch("cli.Path.home", return_value=tmp_path):
            with pytest.raises(SystemExit):
                generate_sandbox_alias("nonexistent")

    def test_no_executables_exits(self, tmp_path):
        """Exits with error if no executables found."""
        overlay_dir = tmp_path / ".local" / "state" / "bui" / "overlays" / "test"
        overlay_dir.mkdir(parents=True)
        # Create a non-executable file
        (overlay_dir / "readme.txt").write_text("readme")

        with patch("cli.Path.home", return_value=tmp_path):
            with pytest.raises(SystemExit):
                generate_sandbox_alias("test")

    def test_generates_alias(self, tmp_path, capsys):
        """Generates alias for selected executable."""
        overlay_dir = tmp_path / ".local" / "state" / "bui" / "overlays" / "deno"
        overlay_dir.mkdir(parents=True)

        # Create executable
        exe = overlay_dir / ".deno" / "bin" / "deno"
        exe.parent.mkdir(parents=True)
        exe.write_text("#!/bin/bash")
        exe.chmod(0o755)

        with patch("cli.Path.home", return_value=tmp_path):
            with patch("builtins.input", return_value="1"):
                generate_sandbox_alias("deno")

        captured = capsys.readouterr()
        assert "Executables in sandbox 'deno':" in captured.out
        assert ".deno/bin/deno" in captured.out
        assert "alias deno='bui --profile untrusted --sandbox deno --bind-cwd -- ~/.deno/bin/deno'" in captured.out

    def test_invalid_selection_exits(self, tmp_path):
        """Exits with error on invalid selection."""
        overlay_dir = tmp_path / ".local" / "state" / "bui" / "overlays" / "test"
        overlay_dir.mkdir(parents=True)

        exe = overlay_dir / "bin" / "app"
        exe.parent.mkdir()
        exe.write_text("#!/bin/bash")
        exe.chmod(0o755)

        with patch("cli.Path.home", return_value=tmp_path):
            with patch("builtins.input", return_value="invalid"):
                with pytest.raises(SystemExit):
                    generate_sandbox_alias("test")
