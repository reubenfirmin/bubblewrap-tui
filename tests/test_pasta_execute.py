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
from net.filtering import create_init_script, validate_filtering_requirements
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

    @patch("net.utils.find_cap_drop_tool")
    @patch("net.iptables.find_iptables")
    def test_exits_when_ip6tables_missing_but_needed(
        self, mock_find_iptables, mock_find_cap_drop
    ):
        """Exits when IPv6 filtering needed but no ip6tables."""
        mock_find_iptables.return_value = ("/usr/bin/iptables", None, False)
        mock_find_cap_drop.return_value = ("/usr/bin/setpriv", "exec setpriv ...")

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

    @patch("net.filtering.find_cap_drop_tool")
    @patch("net.iptables.find_iptables")
    def test_exits_when_cap_drop_tool_missing(
        self, mock_find_iptables, mock_find_cap_drop
    ):
        """Exits when no setpriv/capsh available."""
        mock_find_iptables.return_value = (
            "/usr/bin/iptables",
            "/usr/bin/ip6tables",
            False,
        )
        mock_find_cap_drop.return_value = (None, "")

        nf = NetworkFilter(mode=NetworkMode.FILTER)

        with pytest.raises(SystemExit) as exc_info:
            validate_filtering_requirements(nf)
        assert exc_info.value.code == 1

    @patch("net.filtering.find_cap_drop_tool")
    @patch("net.iptables.find_iptables")
    def test_returns_paths_when_all_available(
        self, mock_find_iptables, mock_find_cap_drop
    ):
        """Returns (iptables, ip6tables, is_multicall, template) when all available."""
        mock_find_iptables.return_value = (
            "/usr/bin/iptables",
            "/usr/bin/ip6tables",
            False,
        )
        mock_find_cap_drop.return_value = (
            "/usr/bin/setpriv",
            "exec setpriv --bounding-set=-net_admin -- {command}",
        )

        nf = NetworkFilter(mode=NetworkMode.FILTER)
        result = validate_filtering_requirements(nf)

        assert result[0] == "/usr/bin/iptables"
        assert result[1] == "/usr/bin/ip6tables"
        assert result[2] is False
        assert "{command}" in result[3]

    @patch("net.filtering.find_cap_drop_tool")
    @patch("net.iptables.find_iptables")
    def test_allows_missing_ip6tables_for_ipv4_only(
        self, mock_find_iptables, mock_find_cap_drop
    ):
        """Doesn't require ip6tables for IPv4-only filters."""
        mock_find_iptables.return_value = ("/usr/bin/iptables", None, False)
        mock_find_cap_drop.return_value = (
            "/usr/bin/setpriv",
            "exec setpriv --bounding-set=-net_admin -- {command}",
        )

        # IPv4 only filter
        nf = NetworkFilter(
            mode=NetworkMode.FILTER,
            ip_filter=IPFilter(mode=FilterMode.WHITELIST, cidrs=["10.0.0.0/8"]),
        )

        result = validate_filtering_requirements(nf)
        assert result[0] == "/usr/bin/iptables"
        assert result[1] is None  # ip6tables not required


class TestCreateInitScript:
    """Tests for create_init_script function."""

    def test_creates_executable_script(self, tmp_path):
        """Script has 755 permissions."""
        nf = NetworkFilter(
            mode=NetworkMode.FILTER,
            ip_filter=IPFilter(mode=FilterMode.WHITELIST, cidrs=["8.8.8.8"]),
        )

        with patch("tempfile.mkdtemp", return_value=str(tmp_path)):
            script_path = create_init_script(
                nf,
                user_command=["echo", "hello"],
                iptables_path="/usr/bin/iptables",
                ip6tables_path="/usr/bin/ip6tables",
                is_multicall=False,
                cap_drop_template="exec setpriv --bounding-set=-net_admin -- {command}",
            )

        assert script_path.exists()
        mode = script_path.stat().st_mode
        assert mode & stat.S_IXUSR  # Owner execute
        assert mode & stat.S_IXGRP  # Group execute
        assert mode & stat.S_IXOTH  # Other execute

    def test_script_contains_iptables_rules(self, tmp_path):
        """Script includes iptables commands."""
        nf = NetworkFilter(
            mode=NetworkMode.FILTER,
            ip_filter=IPFilter(mode=FilterMode.WHITELIST, cidrs=["8.8.8.8"]),
        )

        with patch("tempfile.mkdtemp", return_value=str(tmp_path)):
            script_path = create_init_script(
                nf,
                user_command=["bash"],
                iptables_path="/usr/bin/iptables",
                ip6tables_path="/usr/bin/ip6tables",
                is_multicall=False,
                cap_drop_template="exec setpriv --bounding-set=-net_admin -- {command}",
            )

        content = script_path.read_text()
        assert "/usr/bin/iptables" in content
        assert "-j ACCEPT" in content or "-j DROP" in content

    def test_script_contains_user_command_quoted(self, tmp_path):
        """Script includes user command properly quoted."""
        nf = NetworkFilter(mode=NetworkMode.FILTER)

        with patch("tempfile.mkdtemp", return_value=str(tmp_path)):
            script_path = create_init_script(
                nf,
                user_command=["python", "-c", "print('hello world')"],
                iptables_path="/usr/bin/iptables",
                ip6tables_path="/usr/bin/ip6tables",
                is_multicall=False,
                cap_drop_template="exec setpriv --bounding-set=-net_admin -- {command}",
            )

        content = script_path.read_text()
        assert "python" in content
        # Should be quoted to handle spaces/special chars
        assert "print" in content

    def test_script_contains_cap_drop(self, tmp_path):
        """Script includes capability drop command."""
        nf = NetworkFilter(mode=NetworkMode.FILTER)

        with patch("tempfile.mkdtemp", return_value=str(tmp_path)):
            script_path = create_init_script(
                nf,
                user_command=["bash"],
                iptables_path="/usr/bin/iptables",
                ip6tables_path="/usr/bin/ip6tables",
                is_multicall=False,
                cap_drop_template="exec setpriv --bounding-set=-net_admin -- {command}",
            )

        content = script_path.read_text()
        assert "setpriv" in content
        assert "net_admin" in content

    def test_returns_path_to_script(self, tmp_path):
        """Returns Path object to created script."""
        nf = NetworkFilter(mode=NetworkMode.FILTER)

        with patch("tempfile.mkdtemp", return_value=str(tmp_path)):
            script_path = create_init_script(
                nf,
                user_command=["bash"],
                iptables_path="/usr/bin/iptables",
                ip6tables_path="/usr/bin/ip6tables",
                is_multicall=False,
                cap_drop_template="exec {command}",
            )

        assert isinstance(script_path, Path)
        assert script_path.name == "init.sh"


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

    def test_removes_cap_drop_net_admin(self):
        """Removes --cap-drop CAP_NET_ADMIN pair."""
        cmd = [
            "bwrap",
            "--cap-drop",
            "CAP_NET_ADMIN",
            "--cap-drop",
            "CAP_SYS_ADMIN",
            "--",
            "bash",
        ]
        result = prepare_bwrap_command(cmd, "/tmp/test")
        # CAP_NET_ADMIN should be removed, CAP_SYS_ADMIN should remain
        assert "CAP_NET_ADMIN" not in result or result[
            result.index("CAP_NET_ADMIN") - 1
        ] != "--cap-drop"
        assert "CAP_SYS_ADMIN" in result

    def test_adds_cap_add_net_admin(self):
        """Adds --cap-add CAP_NET_ADMIN."""
        cmd = ["bwrap", "--ro-bind", "/usr", "/usr", "--", "bash"]
        result = prepare_bwrap_command(cmd, "/tmp/test")
        assert "--cap-add" in result
        cap_add_idx = result.index("--cap-add")
        assert result[cap_add_idx + 1] == "CAP_NET_ADMIN"

    def test_exits_when_no_separator(self):
        """Exits with error when no -- separator found."""
        cmd = ["bwrap", "--ro-bind", "/usr", "/usr", "bash"]  # Missing --
        with pytest.raises(SystemExit) as exc_info:
            prepare_bwrap_command(cmd, "/tmp/test")
        assert exc_info.value.code == 1

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
            return ["bwrap", "--unshare-net", "--ro-bind", "/usr", "/usr", "--"] + config.command

        return build_fn

    @patch("sys.exit")
    @patch("subprocess.Popen")
    @patch("commandoutput.print_execution_header")
    @patch("net.pasta_exec.create_init_script")
    @patch("net.pasta_exec.validate_filtering_requirements")
    def test_validates_requirements_before_execution(
        self,
        mock_validate,
        mock_create_script,
        mock_print_header,
        mock_popen,
        mock_exit,
        minimal_config,
        mock_build_command,
        tmp_path,
    ):
        """Calls validation function before proceeding."""
        mock_validate.return_value = (
            "/usr/bin/iptables",
            "/usr/bin/ip6tables",
            False,
            "exec {command}",
        )
        mock_create_script.return_value = tmp_path / "init.sh"
        (tmp_path / "init.sh").write_text("#!/bin/sh\necho test")
        mock_popen.return_value = MagicMock(wait=MagicMock(return_value=0), poll=MagicMock(return_value=0))

        from net.pasta_exec import execute_with_pasta

        execute_with_pasta(minimal_config, None, mock_build_command)

        mock_validate.assert_called_once_with(minimal_config.network_filter)

    @patch("sys.exit")
    @patch("subprocess.Popen")
    @patch("commandoutput.print_execution_header")
    @patch("net.pasta_exec.create_init_script")
    @patch("net.pasta_exec.validate_filtering_requirements")
    def test_creates_init_script(
        self,
        mock_validate,
        mock_create_script,
        mock_print_header,
        mock_popen,
        mock_exit,
        minimal_config,
        mock_build_command,
        tmp_path,
    ):
        """Creates init script with correct content."""
        mock_validate.return_value = (
            "/usr/bin/iptables",
            "/usr/bin/ip6tables",
            False,
            "exec {command}",
        )
        script_path = tmp_path / "init.sh"
        script_path.write_text("#!/bin/sh\necho test")
        mock_create_script.return_value = script_path
        mock_popen.return_value = MagicMock(wait=MagicMock(return_value=0), poll=MagicMock(return_value=0))

        from net.pasta_exec import execute_with_pasta

        execute_with_pasta(minimal_config, None, mock_build_command)

        mock_create_script.assert_called_once()

    @patch("sys.exit")
    @patch("subprocess.Popen")
    @patch("commandoutput.print_execution_header")
    @patch("net.pasta_exec.create_init_script")
    @patch("net.pasta_exec.validate_filtering_requirements")
    def test_calls_popen_with_pasta(
        self,
        mock_validate,
        mock_create_script,
        mock_print_header,
        mock_popen,
        mock_exit,
        minimal_config,
        mock_build_command,
        tmp_path,
    ):
        """Calls subprocess.Popen with pasta command."""
        mock_validate.return_value = (
            "/usr/bin/iptables",
            "/usr/bin/ip6tables",
            False,
            "exec {command}",
        )
        script_path = tmp_path / "init.sh"
        script_path.write_text("#!/bin/sh\necho test")
        mock_create_script.return_value = script_path
        mock_popen.return_value = MagicMock(wait=MagicMock(return_value=0), poll=MagicMock(return_value=0))

        from net.pasta_exec import execute_with_pasta

        execute_with_pasta(minimal_config, None, mock_build_command)

        mock_popen.assert_called_once()
        args = mock_popen.call_args[0][0]  # First positional arg is the command list
        assert args[0] == "pasta"  # First element is program name
        assert "--" in args  # Separator is in command list

    @patch("net.pasta_exec.create_init_script")
    @patch("net.pasta_exec.validate_filtering_requirements")
    def test_handles_hostname_resolution_error(
        self, mock_validate, mock_create_script, minimal_config, mock_build_command
    ):
        """Exits cleanly on DNS failure."""
        from net.utils import HostnameResolutionError

        mock_validate.return_value = (
            "/usr/bin/iptables",
            "/usr/bin/ip6tables",
            False,
            "exec {command}",
        )
        mock_create_script.side_effect = HostnameResolutionError(
            "Failed to resolve 'bad.hostname'"
        )

        from net.pasta_exec import execute_with_pasta

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
        """Exits with code 130 on Ctrl+C."""
        mock_mkdtemp.return_value = str(tmp_path)
        mock_run.side_effect = KeyboardInterrupt()

        from net.pasta_exec import execute_with_audit

        execute_with_audit(audit_config, None, mock_build_command)

        mock_exit.assert_called_with(130)


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
