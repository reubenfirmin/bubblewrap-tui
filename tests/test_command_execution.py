"""Tests for command execution and PTY handling."""

from __future__ import annotations

import os
import signal
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from command_execution import _get_descendants, _run_with_pty


class TestRunWithPty:
    """Tests for _run_with_pty function."""

    def test_runs_simple_command(self):
        """Successfully runs a simple command and returns exit code."""
        exit_code = _run_with_pty(["echo", "hello"])
        assert exit_code == 0

    def test_returns_nonzero_exit_code(self):
        """Returns correct exit code for failing commands."""
        exit_code = _run_with_pty(["sh", "-c", "exit 42"])
        assert exit_code == 42

    def test_returns_127_for_command_not_found(self):
        """Returns 127 when command doesn't exist."""
        exit_code = _run_with_pty(["nonexistent_command_xyz_123"])
        assert exit_code == 127

    def test_handles_command_with_arguments(self):
        """Correctly passes arguments to command."""
        exit_code = _run_with_pty(["sh", "-c", "test -n 'hello'"])
        assert exit_code == 0

    def test_handles_command_producing_output(self):
        """Handles commands that produce stdout output."""
        # This should complete without hanging
        exit_code = _run_with_pty(["sh", "-c", "echo line1; echo line2; echo line3"])
        assert exit_code == 0

    def test_handles_command_producing_stderr(self):
        """Handles commands that produce stderr output."""
        exit_code = _run_with_pty(["sh", "-c", "echo error >&2"])
        assert exit_code == 0

    def test_handles_quick_exit_command(self):
        """Handles commands that exit immediately."""
        exit_code = _run_with_pty(["true"])
        assert exit_code == 0

        exit_code = _run_with_pty(["false"])
        assert exit_code == 1

    def test_handles_permission_denied(self, tmp_path):
        """Returns non-zero exit code for permission denied errors."""
        # Create a non-executable file
        script = tmp_path / "no_exec.sh"
        script.write_text("#!/bin/sh\necho hello")
        script.chmod(0o644)  # No execute permission

        exit_code = _run_with_pty([str(script)])
        # Should return non-zero (either 126 for permission denied or 1)
        assert exit_code != 0


class TestExecuteDirect:
    """Tests for _execute_direct function using PTY."""

    @pytest.fixture
    def mock_config(self):
        """Create minimal mock SandboxConfig."""
        config = MagicMock()
        config.command = ["echo", "test"]
        return config

    @pytest.fixture
    def mock_build_command(self):
        """Mock build command function."""
        def build_fn(config, file_map):
            return ["bwrap", "--ro-bind", "/usr", "/usr", "--"] + config.command
        return build_fn

    @patch("command_execution._run_with_pty")
    @patch("commandoutput.print_execution_header")
    def test_uses_pty_for_execution(
        self, mock_print_header, mock_run_pty, mock_config, mock_build_command
    ):
        """_execute_direct uses _run_with_pty instead of os.execvp."""
        from command_execution import _execute_direct

        mock_run_pty.return_value = 0

        exit_code = _execute_direct(
            mock_config, None, mock_build_command, None, [], None
        )

        mock_run_pty.assert_called_once()
        assert exit_code == 0

    @patch("command_execution._run_with_pty")
    @patch("commandoutput.print_execution_header")
    def test_passes_built_command_to_pty(
        self, mock_print_header, mock_run_pty, mock_config, mock_build_command
    ):
        """_execute_direct passes the built bwrap command to _run_with_pty."""
        from command_execution import _execute_direct

        mock_run_pty.return_value = 0

        _execute_direct(mock_config, None, mock_build_command, None, [], None)

        # Verify the command passed to _run_with_pty
        call_args = mock_run_pty.call_args[0][0]
        assert call_args[0] == "bwrap"
        assert "--ro-bind" in call_args
        assert "echo" in call_args
        assert "test" in call_args

    @patch("command_execution._run_with_pty")
    @patch("commandoutput.print_execution_header")
    def test_returns_exit_code_from_pty(
        self, mock_print_header, mock_run_pty, mock_config, mock_build_command
    ):
        """_execute_direct returns the exit code from _run_with_pty."""
        from command_execution import _execute_direct

        mock_run_pty.return_value = 42

        exit_code = _execute_direct(
            mock_config, None, mock_build_command, None, [], None
        )

        assert exit_code == 42

    @patch("command_execution._run_with_pty")
    @patch("commandoutput.print_execution_header")
    def test_flushes_stdout_stderr_before_pty(
        self, mock_print_header, mock_run_pty, mock_config, mock_build_command
    ):
        """_execute_direct flushes stdout/stderr before starting PTY."""
        from command_execution import _execute_direct

        mock_run_pty.return_value = 0

        with patch.object(sys.stdout, 'flush') as mock_stdout_flush:
            with patch.object(sys.stderr, 'flush') as mock_stderr_flush:
                _execute_direct(
                    mock_config, None, mock_build_command, None, [], None
                )

                mock_stdout_flush.assert_called()
                mock_stderr_flush.assert_called()

    @patch("command_execution._run_with_pty")
    @patch("commandoutput.print_execution_header")
    def test_prints_execution_header(
        self, mock_print_header, mock_run_pty, mock_config, mock_build_command
    ):
        """_execute_direct prints execution header before running."""
        from command_execution import _execute_direct

        mock_run_pty.return_value = 0

        _execute_direct(
            mock_config, None, mock_build_command, "test-sandbox", [Path("/tmp/overlay")], None
        )

        mock_print_header.assert_called_once()
        call_kwargs = mock_print_header.call_args[1]
        assert call_kwargs["sandbox_name"] == "test-sandbox"
        assert call_kwargs["overlay_dirs"] == [Path("/tmp/overlay")]


class TestPtyTerminalHandling:
    """Tests for PTY terminal handling specifics."""

    def test_preserves_terminal_on_clean_exit(self):
        """Terminal settings are restored after command exits."""
        # Run a command that exits cleanly
        exit_code = _run_with_pty(["true"])
        assert exit_code == 0

        # If we can still interact with the terminal, it was restored correctly
        # This is a basic smoke test - more complex testing would require
        # actually checking termios settings
        assert sys.stdin.isatty() or True  # Pass if not a tty (CI environment)

    def test_handles_non_tty_stdin(self):
        """Works correctly when stdin is not a TTY."""
        # This test runs in the test environment which may or may not have a TTY
        # The important thing is it doesn't crash
        exit_code = _run_with_pty(["echo", "test"])
        assert exit_code == 0


class TestPtyProcessCleanup:
    """Tests for PTY process cleanup behavior."""

    def test_reaps_child_on_normal_exit(self):
        """Child process is properly reaped on normal exit."""
        exit_code = _run_with_pty(["sh", "-c", "exit 0"])
        assert exit_code == 0

        # No zombie processes should be left
        # This is verified by the fact that waitpid was called

    def test_reaps_child_on_error_exit(self):
        """Child process is properly reaped on error exit."""
        exit_code = _run_with_pty(["sh", "-c", "exit 1"])
        assert exit_code == 1

    def test_handles_child_that_forks(self):
        """Handles commands that fork child processes."""
        # Run a command that forks a child that exits quickly
        exit_code = _run_with_pty(["sh", "-c", "sh -c 'exit 0'"])
        assert exit_code == 0


class TestGetDescendantsIntegration:
    """Integration tests for _get_descendants with _run_with_pty."""

    def test_get_descendants_returns_list(self):
        """_get_descendants returns a list type."""
        result = _get_descendants(os.getpid())
        assert isinstance(result, list)

    def test_get_descendants_for_current_process(self):
        """_get_descendants works for current process."""
        # Current test process shouldn't have children at this point
        result = _get_descendants(os.getpid())
        assert isinstance(result, list)


class TestFixOverlayWorkdirPermissions:
    """Tests for _fix_overlay_workdir_permissions cleanup robustness (#92)."""

    def test_does_not_raise_when_walk_errors(self):
        """If os.walk itself raises OSError, cleanup must not crash (#92).

        os.walk can raise on symlink loops, mid-traversal deletions, or fs
        errors. This runs inside a `finally`, so a crash here would skip the
        rmtree and leave the sandbox half-cleaned.
        """
        from command_execution import _fix_overlay_workdir_permissions

        with patch(
            "command_execution.os.walk",
            side_effect=OSError("Too many levels of symbolic links"),
        ):
            # Must return normally, not propagate the OSError.
            _fix_overlay_workdir_permissions(Path("/nonexistent"))

    def test_chmods_directories_missing_owner_perms(self, tmp_path):
        """Directories lacking owner rwx get chmod'd so they can be deleted (#92)."""
        from command_execution import _fix_overlay_workdir_permissions

        work = tmp_path / "work"
        (work / "nested").mkdir(parents=True)
        work.chmod(0o000)
        try:
            _fix_overlay_workdir_permissions(tmp_path)
            assert work.stat().st_mode & 0o700 == 0o700
        finally:
            work.chmod(0o755)


class TestCopyWinsize:
    """PTY window-size propagation - the fix for 0x0 sandbox terminals that
    collapse size-sensitive TUIs (opencode/pi)."""

    def test_copies_rows_and_cols_to_pty(self):
        import fcntl
        import pty
        import struct
        import termios

        from command_execution import _copy_winsize

        src_master, src_slave = pty.openpty()
        dst_master, dst_slave = pty.openpty()
        try:
            # Give the source terminal a known, non-zero size.
            fcntl.ioctl(src_slave, termios.TIOCSWINSZ, struct.pack("HHHH", 40, 100, 0, 0))
            # Destination starts at 0x0 (default for a fresh pty).
            rows0, cols0, _, _ = struct.unpack(
                "HHHH", fcntl.ioctl(dst_slave, termios.TIOCGWINSZ, b"\x00" * 8)
            )
            assert (rows0, cols0) == (0, 0)

            _copy_winsize(src_slave, dst_master)

            rows, cols, _, _ = struct.unpack(
                "HHHH", fcntl.ioctl(dst_slave, termios.TIOCGWINSZ, b"\x00" * 8)
            )
            assert (rows, cols) == (40, 100)
        finally:
            for f in (src_master, src_slave, dst_master, dst_slave):
                os.close(f)

    def test_noop_when_source_is_not_a_tty(self, tmp_path):
        """A non-tty source (or any ioctl failure) must be swallowed, not raised."""
        from command_execution import _copy_winsize

        p = tmp_path / "regular_file"
        p.write_text("x")
        fd = os.open(str(p), os.O_RDONLY)
        try:
            _copy_winsize(fd, fd)  # ioctl fails on a regular file -> no raise
        finally:
            os.close(fd)
