"""Tests for pasta execution functions in net/pasta.py and related modules."""

from __future__ import annotations

import os
import stat
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

from model.network_filter import (
    AuditConfig,
    FilterMode,
    HostnameFilter,
    IPFilter,
    NetworkFilter,
    NetworkMode,
    PortForwarding,
)
from model.sandbox_config import SandboxConfig
from net.filtering import validate_filtering_requirements
from net.pasta_args import prepare_bwrap_command


class TestValidateFilteringRequirements:
    """Tests for validate_filtering_requirements function."""

    @patch("net.iptables.find_iptables")
    def test_exits_when_iptables_missing(self, mock_find_iptables):
        """Calls sys.exit when iptables not found."""
        mock_find_iptables.return_value = (None, None, False)
        nf = NetworkFilter(mode=NetworkMode.FILTER)

        with pytest.raises(SystemExit) as exc_info:
            validate_filtering_requirements(nf)
        assert exc_info.value.code == 1

    @patch("net.iptables.find_iptables")
    def test_exits_when_ip6tables_missing_but_needed(self, mock_find_iptables):
        """Exits when IPv6 filtering needed but no ip6tables."""
        mock_find_iptables.return_value = ("/usr/bin/iptables", None, False)

        # Hostname filter enables IPv6 filtering
        nf = NetworkFilter(
            mode=NetworkMode.FILTER,
            hostname_filter=HostnameFilter(
                mode=FilterMode.WHITELIST, hosts=["example.com"]
            ),
        )

        with pytest.raises(SystemExit) as exc_info:
            validate_filtering_requirements(nf)
        assert exc_info.value.code == 1

    @patch("net.iptables.find_iptables")
    def test_returns_paths_when_all_available(self, mock_find_iptables):
        """Returns (iptables, ip6tables, is_multicall) when all available."""
        mock_find_iptables.return_value = (
            "/usr/bin/iptables",
            "/usr/bin/ip6tables",
            False,
        )

        nf = NetworkFilter(mode=NetworkMode.FILTER)
        result = validate_filtering_requirements(nf)

        assert result[0] == "/usr/bin/iptables"
        assert result[1] == "/usr/bin/ip6tables"
        assert result[2] is False

    @patch("net.iptables.find_iptables")
    def test_allows_missing_ip6tables_for_ipv4_only(self, mock_find_iptables):
        """Doesn't require ip6tables for IPv4-only filters."""
        mock_find_iptables.return_value = ("/usr/bin/iptables", None, False)

        # IPv4 only filter
        nf = NetworkFilter(
            mode=NetworkMode.FILTER,
            ip_filter=IPFilter(mode=FilterMode.WHITELIST, cidrs=["10.0.0.0/8"]),
        )

        result = validate_filtering_requirements(nf)
        assert result[0] == "/usr/bin/iptables"
        assert result[1] is None  # ip6tables not required


class TestPrepareBwrapCommand:
    """Tests for prepare_bwrap_command function."""

    def test_removes_unshare_net(self):
        """Removes --unshare-net from command."""
        cmd = ["bwrap", "--unshare-net", "--ro-bind", "/usr", "/usr", "--", "bash"]
        result = prepare_bwrap_command(cmd, "/tmp/test")
        assert "--unshare-net" not in result

    def test_adds_tmp_dir_bind(self):
        """Adds --bind for temp directory."""
        cmd = ["bwrap", "--ro-bind", "/usr", "/usr", "--", "bash"]
        result = prepare_bwrap_command(cmd, "/tmp/bui-net-xyz")
        assert "--bind" in result
        assert "/tmp/bui-net-xyz" in result

    def test_keeps_unshare_user(self):
        """Keeps --unshare-user in command (needed for --disable-userns)."""
        cmd = ["bwrap", "--unshare-user", "--unshare-net", "--ro-bind", "/usr", "/usr", "--", "bash"]
        result = prepare_bwrap_command(cmd, "/tmp/test")
        assert "--unshare-user" in result

    def test_keeps_disable_userns(self):
        """Keeps --disable-userns in command."""
        cmd = ["bwrap", "--unshare-user", "--disable-userns", "--ro-bind", "/usr", "/usr", "--", "bash"]
        result = prepare_bwrap_command(cmd, "/tmp/test")
        assert "--disable-userns" in result

    def test_preserves_other_arguments(self):
        """Preserves other bwrap arguments."""
        cmd = [
            "bwrap",
            "--unshare-net",
            "--ro-bind",
            "/usr",
            "/usr",
            "--bind",
            "/home",
            "/home",
            "--proc",
            "/proc",
            "--",
            "bash",
            "-c",
            "echo hello",
        ]
        result = prepare_bwrap_command(cmd, "/tmp/test")
        assert "--ro-bind" in result
        assert "--proc" in result
        assert "bash" in result
        assert "-c" in result
        assert "echo hello" in result


class TestExecuteWithPasta:
    """Integration tests for execute_with_pasta with mocks."""

    @pytest.fixture
    def minimal_config(self):
        """Create minimal SandboxConfig for testing."""
        config = SandboxConfig(command=["echo", "test"])
        config.network_filter = NetworkFilter(
            mode=NetworkMode.FILTER,
            ip_filter=IPFilter(mode=FilterMode.WHITELIST, cidrs=["8.8.8.8"]),
        )
        return config

    @pytest.fixture
    def mock_build_command(self):
        """Mock build command function."""

        def build_fn(config, file_map):
            return ["bwrap", "--unshare-net", "--unshare-user", "--ro-bind", "/usr", "/usr", "--"] + config.command

        return build_fn

    @patch("net.pasta_exec._run_with_pty")
    @patch("commandoutput.print_execution_header")
    @patch("net.pasta_exec.validate_filtering_requirements")
    def test_validates_requirements_before_execution(
        self,
        mock_validate,
        mock_print_header,
        mock_run_pty,
        minimal_config,
        mock_build_command,
    ):
        """Calls validation function before proceeding."""
        mock_validate.return_value = (
            "/usr/bin/iptables",
            "/usr/bin/ip6tables",
            False,
        )
        mock_run_pty.return_value = 0

        from net.pasta_exec import execute_with_pasta

        execute_with_pasta(minimal_config, None, mock_build_command)

        mock_validate.assert_called_once_with(minimal_config.network_filter)

    @patch("net.pasta_exec._run_with_pty")
    @patch("commandoutput.print_execution_header")
    @patch("net.pasta_exec.validate_filtering_requirements")
    def test_creates_wrapper_script(
        self,
        mock_validate,
        mock_print_header,
        mock_run_pty,
        minimal_config,
        mock_build_command,
        tmp_path,
    ):
        """Creates wrapper script in temp directory."""
        mock_validate.return_value = (
            "/usr/bin/iptables",
            "/usr/bin/ip6tables",
            False,
        )
        mock_run_pty.return_value = 0

        from net.pasta_exec import execute_with_pasta

        with patch("tempfile.mkdtemp", return_value=str(tmp_path)):
            execute_with_pasta(minimal_config, None, mock_build_command)

        # Wrapper script should be created
        wrapper_path = tmp_path / "wrapper.sh"
        assert wrapper_path.exists()

    @patch("net.pasta_exec.validate_filtering_requirements")
    def test_handles_hostname_resolution_error(
        self, mock_validate, minimal_config, mock_build_command
    ):
        """Exits cleanly on DNS failure."""
        from net.utils import HostnameResolutionError

        mock_validate.return_value = (
            "/usr/bin/iptables",
            "/usr/bin/ip6tables",
            False,
        )

        from net.pasta_exec import execute_with_pasta

        # Mock create_wrapper_script to raise HostnameResolutionError
        with patch("net.pasta_exec.create_wrapper_script") as mock_create:
            mock_create.side_effect = HostnameResolutionError(
                "Failed to resolve 'bad.hostname'"
            )

            with pytest.raises(SystemExit) as exc_info:
                execute_with_pasta(minimal_config, None, mock_build_command)
            assert exc_info.value.code == 1


class TestExecuteWithAudit:
    """Integration tests for execute_with_audit with mocks."""

    @pytest.fixture
    def audit_config(self):
        """Create SandboxConfig with audit mode."""
        config = SandboxConfig(command=["curl", "example.com"])
        config.network_filter = NetworkFilter(mode=NetworkMode.AUDIT)
        return config

    @pytest.fixture
    def mock_build_command(self):
        """Mock build command function."""

        def build_fn(config, file_map):
            return ["bwrap", "--unshare-net", "--ro-bind", "/usr", "/usr", "--"] + config.command

        return build_fn

    @patch("sys.exit")
    @patch("net.audit.print_audit_summary")
    @patch("net.audit.parse_pcap")
    @patch("subprocess.run")
    @patch("commandoutput.print_audit_header")
    @patch("tempfile.mkdtemp")
    def test_creates_pcap_directory(
        self,
        mock_mkdtemp,
        mock_print_header,
        mock_run,
        mock_parse_pcap,
        mock_print_summary,
        mock_exit,
        audit_config,
        mock_build_command,
        tmp_path,
    ):
        """Creates temp directory for pcap."""
        mock_mkdtemp.return_value = str(tmp_path)
        mock_run.return_value = MagicMock(returncode=0)
        mock_parse_pcap.return_value = MagicMock(dest_ips={})

        from net.pasta_exec import execute_with_audit

        execute_with_audit(audit_config, None, mock_build_command)
        mock_mkdtemp.assert_called_once()

    @patch("sys.exit")
    @patch("net.audit.print_audit_summary")
    @patch("net.audit.parse_pcap")
    @patch("subprocess.run")
    @patch("commandoutput.print_audit_header")
    @patch("tempfile.mkdtemp")
    def test_passes_pcap_path_to_pasta(
        self,
        mock_mkdtemp,
        mock_print_header,
        mock_run,
        mock_parse_pcap,
        mock_print_summary,
        mock_exit,
        audit_config,
        mock_build_command,
        tmp_path,
    ):
        """Includes --pcap argument in pasta command."""
        mock_mkdtemp.return_value = str(tmp_path)
        mock_run.return_value = MagicMock(returncode=0)
        mock_parse_pcap.return_value = MagicMock(dest_ips={})

        from net.pasta_exec import execute_with_audit

        execute_with_audit(audit_config, None, mock_build_command)

        # Check subprocess.run was called with --pcap
        call_args = mock_run.call_args[0][0]
        assert "--pcap" in call_args

    @patch("sys.exit")
    @patch("net.audit.print_audit_summary")
    @patch("net.audit.parse_pcap")
    @patch("subprocess.run")
    @patch("commandoutput.print_audit_header")
    @patch("tempfile.mkdtemp")
    def test_parses_pcap_after_execution(
        self,
        mock_mkdtemp,
        mock_print_header,
        mock_run,
        mock_parse_pcap,
        mock_print_summary,
        mock_exit,
        audit_config,
        mock_build_command,
        tmp_path,
    ):
        """Calls parse_pcap on pcap file after sandbox exits."""
        mock_mkdtemp.return_value = str(tmp_path)
        mock_run.return_value = MagicMock(returncode=0)
        mock_parse_pcap.return_value = MagicMock(dest_ips={})

        # Create a fake pcap file
        pcap_path = tmp_path / "audit.pcap"
        pcap_path.write_bytes(b"fake pcap")

        from net.pasta_exec import execute_with_audit

        execute_with_audit(audit_config, None, mock_build_command)

        mock_parse_pcap.assert_called_once()

    @patch("sys.exit")
    @patch("net.audit.print_audit_summary")
    @patch("net.audit.parse_pcap")
    @patch("subprocess.run")
    @patch("commandoutput.print_audit_header")
    @patch("tempfile.mkdtemp")
    def test_prints_audit_summary(
        self,
        mock_mkdtemp,
        mock_print_header,
        mock_run,
        mock_parse_pcap,
        mock_print_summary,
        mock_exit,
        audit_config,
        mock_build_command,
        tmp_path,
    ):
        """Calls print_audit_summary after parsing."""
        mock_mkdtemp.return_value = str(tmp_path)
        mock_run.return_value = MagicMock(returncode=0)
        mock_result = MagicMock(dest_ips={})
        mock_parse_pcap.return_value = mock_result

        # Create a fake pcap file
        pcap_path = tmp_path / "audit.pcap"
        pcap_path.write_bytes(b"fake pcap")

        from net.pasta_exec import execute_with_audit

        execute_with_audit(audit_config, None, mock_build_command)

        mock_print_summary.assert_called_once()

    @patch("sys.exit")
    @patch("subprocess.run")
    @patch("commandoutput.print_audit_header")
    @patch("tempfile.mkdtemp")
    def test_handles_keyboard_interrupt(
        self,
        mock_mkdtemp,
        mock_print_header,
        mock_run,
        mock_exit,
        audit_config,
        mock_build_command,
        tmp_path,
    ):
        """Returns exit code 130 on Ctrl+C."""
        mock_mkdtemp.return_value = str(tmp_path)
        mock_run.side_effect = KeyboardInterrupt()

        from net.pasta_exec import execute_with_audit

        exit_code = execute_with_audit(audit_config, None, mock_build_command)

        assert exit_code == 130

    @patch("sys.exit")
    @patch("net.audit.print_audit_summary")
    @patch("net.audit.parse_pcap")
    @patch("subprocess.run")
    @patch("commandoutput.print_audit_header")
    def test_temp_directory_has_secure_permissions(
        self,
        mock_print_header,
        mock_run,
        mock_parse_pcap,
        mock_print_summary,
        mock_exit,
        audit_config,
        mock_build_command,
    ):
        """Temp directory is created with 0o700 (not world-writable)."""
        import tempfile

        mock_run.return_value = MagicMock(returncode=0)
        mock_parse_pcap.return_value = MagicMock(dest_ips={})

        from net.pasta_exec import execute_with_audit

        # Track the temp directory created
        created_dirs = []
        original_mkdtemp = tempfile.mkdtemp

        def tracking_mkdtemp(*args, **kwargs):
            result = original_mkdtemp(*args, **kwargs)
            created_dirs.append(result)
            return result

        with patch("tempfile.mkdtemp", side_effect=tracking_mkdtemp):
            execute_with_audit(audit_config, None, mock_build_command)

        # Verify at least one temp dir was created
        assert len(created_dirs) >= 1
        tmp_dir = Path(created_dirs[0])

        # Check permissions are 0o700 (owner only), NOT 0o777 (world-writable)
        if tmp_dir.exists():
            mode = tmp_dir.stat().st_mode & 0o777
            assert mode == 0o700, f"Expected 0o700 but got {oct(mode)}"


class TestFindIptables:
    """Tests for find_iptables function."""

    @patch("shutil.which")
    @patch("os.path.realpath")
    def test_finds_standard_iptables(self, mock_realpath, mock_which):
        """Finds standard iptables binaries."""
        mock_which.side_effect = lambda x: f"/usr/bin/{x}" if x in ["iptables", "ip6tables"] else None
        mock_realpath.side_effect = lambda x: x

        from net.iptables import find_iptables

        v4, v6, multicall = find_iptables()
        assert v4 == "/usr/bin/iptables"
        assert v6 == "/usr/bin/ip6tables"
        assert multicall is False

    @patch("shutil.which")
    @patch("os.path.realpath")
    def test_detects_multicall_binary(self, mock_realpath, mock_which):
        """Detects xtables-nft-multi multicall binary."""
        mock_which.side_effect = lambda x: "/usr/bin/iptables" if x in ["iptables", "ip6tables"] else None
        mock_realpath.return_value = "/usr/lib/xtables-nft-multi"

        from net.iptables import find_iptables

        v4, v6, multicall = find_iptables()
        assert "multi" in v4
        assert multicall is True

    @patch("shutil.which")
    def test_returns_none_when_not_found(self, mock_which):
        """Returns None when iptables not installed."""
        mock_which.return_value = None

        from net.iptables import find_iptables

        v4, v6, multicall = find_iptables()
        assert v4 is None
        assert v6 is None
        assert multicall is False


class TestCheckIptables:
    """Tests for check_iptables function."""

    @patch("net.iptables.find_iptables")
    def test_returns_true_when_available(self, mock_find):
        """Returns True when iptables is available."""
        mock_find.return_value = ("/usr/bin/iptables", "/usr/bin/ip6tables", False)

        from net.iptables import check_iptables

        assert check_iptables() is True

    @patch("net.iptables.find_iptables")
    def test_returns_false_when_not_available(self, mock_find):
        """Returns False when iptables not available."""
        mock_find.return_value = (None, None, False)

        from net.iptables import check_iptables

        assert check_iptables() is False
