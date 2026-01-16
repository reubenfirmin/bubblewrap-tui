"""Tests for CLI argument parsing."""

import sys
from unittest.mock import patch

import pytest

from cli import needs_shell_wrap, parse_args


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
            command, profile = parse_args()
            assert command == ["bash"]
            assert profile is None

    def test_command_with_args(self):
        """Command with arguments after --."""
        with patch.object(sys, "argv", ["bui", "--", "python", "script.py", "-v"]):
            command, profile = parse_args()
            assert command == ["python", "script.py", "-v"]

    def test_profile_flag(self):
        """--profile flag is parsed."""
        with patch.object(
            sys, "argv", ["bui", "--profile", "test.json", "--", "bash"]
        ):
            command, profile = parse_args()
            assert command == ["bash"]
            assert profile == "test.json"

    def test_profile_flag_path(self):
        """--profile with full path."""
        with patch.object(
            sys, "argv", ["bui", "--profile", "/home/user/profiles/dev.json", "--", "bash"]
        ):
            command, profile = parse_args()
            assert profile == "/home/user/profiles/dev.json"

    def test_no_separator(self):
        """Command without -- separator."""
        with patch.object(sys, "argv", ["bui", "bash"]):
            command, profile = parse_args()
            assert command == ["bash"]

    def test_shell_wrap_applied(self):
        """Shell metacharacters trigger shell wrap."""
        with patch.object(sys, "argv", ["bui", "--", "cat foo | grep bar"]):
            command, profile = parse_args()
            # shlex.join quotes the argument
            assert command[0] == "/bin/bash"
            assert command[1] == "-c"
            assert "cat foo | grep bar" in command[2]

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
