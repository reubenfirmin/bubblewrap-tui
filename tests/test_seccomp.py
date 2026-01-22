"""Tests for seccomp-based user namespace blocking."""

from __future__ import annotations

import platform
from unittest.mock import patch

import pytest

from model.network_filter import (
    FilterMode,
    IPFilter,
    NetworkFilter,
    NetworkMode,
)
from model.sandbox_config import SandboxConfig
from model.serializers import isolation_to_summary
from seccomp import (
    SYSCALL_NUMBERS,
    AUDIT_ARCH,
    CLONE_NEWUSER,
    generate_seccomp_script,
    get_seccomp_init_commands,
)


class TestSeccompConstants:
    """Tests for seccomp module constants."""

    def test_syscall_numbers_x86_64(self):
        """Verify x86_64 syscall numbers are correct."""
        nums = SYSCALL_NUMBERS["x86_64"]
        assert nums["clone"] == 56
        assert nums["clone3"] == 435
        assert nums["unshare"] == 272

    def test_syscall_numbers_aarch64(self):
        """Verify aarch64 syscall numbers are correct."""
        nums = SYSCALL_NUMBERS["aarch64"]
        assert nums["clone"] == 220
        assert nums["clone3"] == 435
        assert nums["unshare"] == 97

    def test_audit_arch_values(self):
        """Verify audit architecture values."""
        assert AUDIT_ARCH["x86_64"] == 0xC000003E
        assert AUDIT_ARCH["aarch64"] == 0xC00000B7

    def test_clone_newuser_flag(self):
        """Verify CLONE_NEWUSER flag value."""
        assert CLONE_NEWUSER == 0x10000000


class TestSeccompScriptGeneration:
    """Tests for seccomp script generation."""

    def test_generate_seccomp_script_not_empty(self):
        """Verify script generation produces output."""
        script = generate_seccomp_script()
        assert script is not None
        assert len(script) > 0

    def test_script_contains_python_exec(self):
        """Verify script uses exec python3 -c pattern."""
        script = generate_seccomp_script()
        assert "exec python3 -c '" in script
        # Script reads command from env var
        assert "SECCOMP_EXEC_CMD" in script

    def test_script_contains_architecture_detection(self):
        """Verify script detects architecture."""
        script = generate_seccomp_script()
        assert "platform.machine()" in script
        assert "x86_64" in script
        assert "aarch64" in script

    def test_script_contains_prctl_calls(self):
        """Verify script uses prctl for seccomp."""
        script = generate_seccomp_script()
        assert "PR_SET_NO_NEW_PRIVS" in script
        assert "PR_SET_SECCOMP" in script
        assert "SECCOMP_MODE_FILTER" in script

    def test_script_contains_bpf_filter_construction(self):
        """Verify script builds BPF filter."""
        script = generate_seccomp_script()
        assert "BPF_LD" in script
        assert "BPF_JMP" in script
        assert "BPF_RET" in script
        assert "CLONE_NEWUSER" in script

    def test_get_seccomp_init_commands_same_as_generate(self):
        """Verify get_seccomp_init_commands returns same script."""
        script1 = generate_seccomp_script()
        script2 = get_seccomp_init_commands()
        assert script1 == script2


class TestSeccompIntegrationWithSandboxConfig:
    """Tests for seccomp integration with SandboxConfig."""

    def test_seccomp_block_userns_field_default(self):
        """Verify seccomp_block_userns defaults to False."""
        config = SandboxConfig()
        assert config.namespace.seccomp_block_userns is False

    def test_seccomp_block_userns_field_settable(self):
        """Verify seccomp_block_userns can be set."""
        config = SandboxConfig()
        config.namespace.seccomp_block_userns = True
        assert config.namespace.seccomp_block_userns is True

    def test_disable_userns_and_seccomp_independent(self):
        """Verify both fields can be set independently."""
        config = SandboxConfig()
        config.namespace.disable_userns = True
        config.namespace.seccomp_block_userns = False
        assert config.namespace.disable_userns is True
        assert config.namespace.seccomp_block_userns is False

        config.namespace.disable_userns = False
        config.namespace.seccomp_block_userns = True
        assert config.namespace.disable_userns is False
        assert config.namespace.seccomp_block_userns is True


class TestSeccompAutoEnableLogic:
    """Tests for automatic seccomp enabling when network filtering + disable_userns conflict."""

    def create_network_filter_with_filtering(self) -> NetworkFilter:
        """Create a NetworkFilter that requires pasta."""
        return NetworkFilter(
            mode=NetworkMode.FILTER,
            ip_filter=IPFilter(mode=FilterMode.WHITELIST, cidrs=["1.2.3.4/32"]),
        )

    def test_use_seccomp_when_explicitly_enabled(self):
        """Seccomp should be used when explicitly enabled."""
        config = SandboxConfig()
        config.namespace.seccomp_block_userns = True
        config.namespace.disable_userns = False
        nf = NetworkFilter()  # No filtering

        use_seccomp = config.namespace.seccomp_block_userns or (
            nf.requires_pasta() and config.namespace.disable_userns
        )
        assert use_seccomp is True

    def test_use_seccomp_when_network_filtering_and_disable_userns(self):
        """Seccomp should be auto-enabled when network filtering + disable_userns."""
        config = SandboxConfig()
        config.namespace.seccomp_block_userns = False
        config.namespace.disable_userns = True
        nf = self.create_network_filter_with_filtering()

        use_seccomp = config.namespace.seccomp_block_userns or (
            nf.requires_pasta() and config.namespace.disable_userns
        )
        assert use_seccomp is True

    def test_no_seccomp_without_network_filtering(self):
        """Seccomp should NOT be auto-enabled without network filtering."""
        config = SandboxConfig()
        config.namespace.seccomp_block_userns = False
        config.namespace.disable_userns = True
        nf = NetworkFilter()  # No filtering (mode=OFF)

        use_seccomp = config.namespace.seccomp_block_userns or (
            nf.requires_pasta() and config.namespace.disable_userns
        )
        assert use_seccomp is False

    def test_no_seccomp_when_neither_enabled(self):
        """Seccomp should NOT be used when neither option is enabled."""
        config = SandboxConfig()
        config.namespace.seccomp_block_userns = False
        config.namespace.disable_userns = False
        nf = self.create_network_filter_with_filtering()

        use_seccomp = config.namespace.seccomp_block_userns or (
            nf.requires_pasta() and config.namespace.disable_userns
        )
        assert use_seccomp is False


class TestSeccompSummaryMessages:
    """Tests for summary messages with seccomp option."""

    def test_summary_shows_seccomp_when_explicitly_enabled(self):
        """Summary should show seccomp when explicitly enabled."""
        config = SandboxConfig()
        config.namespace.seccomp_block_userns = True
        config.namespace.disable_userns = False

        summary = isolation_to_summary(config._isolation_group, None)
        assert "seccomp" in summary.lower()
        assert "DISABLED via seccomp" in summary

    def test_summary_shows_warning_when_auto_enabled(self):
        """Summary should show warning when seccomp is auto-enabled."""
        config = SandboxConfig()
        config.namespace.seccomp_block_userns = False
        config.namespace.disable_userns = True

        # Create network filter that requires pasta
        nf = NetworkFilter(
            mode=NetworkMode.FILTER,
            ip_filter=IPFilter(mode=FilterMode.WHITELIST, cidrs=["1.2.3.4/32"]),
        )

        summary = isolation_to_summary(config._isolation_group, nf)
        assert "auto-enabled" in summary.lower()
        assert "WARNING" in summary

    def test_summary_shows_bwrap_option_without_network_filtering(self):
        """Summary should show bwrap option when no network filtering."""
        config = SandboxConfig()
        config.namespace.seccomp_block_userns = False
        config.namespace.disable_userns = True

        # No network filter
        summary = isolation_to_summary(config._isolation_group, None)
        assert "via seccomp" not in summary
        assert "DISABLED" in summary

    def test_summary_no_warning_when_seccomp_explicit_with_network(self):
        """No warning when seccomp is explicitly enabled (even with network filtering)."""
        config = SandboxConfig()
        config.namespace.seccomp_block_userns = True
        config.namespace.disable_userns = False

        nf = NetworkFilter(
            mode=NetworkMode.FILTER,
            ip_filter=IPFilter(mode=FilterMode.WHITELIST, cidrs=["1.2.3.4/32"]),
        )

        summary = isolation_to_summary(config._isolation_group, nf)
        assert "WARNING" not in summary
        assert "auto-enabled" not in summary.lower()


class TestInitScriptWithSeccomp:
    """Tests for init script generation with seccomp."""

    @patch("net.filtering.find_cap_drop_tool")
    @patch("net.iptables.find_iptables")
    @patch("net.iptables.generate_init_script")
    def test_init_script_includes_seccomp_when_enabled(
        self, mock_iptables_script, mock_find_iptables, mock_find_cap_drop
    ):
        """Init script should include seccomp when use_seccomp=True."""
        mock_find_iptables.return_value = (
            "/usr/bin/iptables",
            "/usr/bin/ip6tables",
            False,
        )
        mock_find_cap_drop.return_value = (
            "/usr/bin/setpriv",
            "exec setpriv --bounding-set=-net_admin -- {command}",
        )
        mock_iptables_script.return_value = "# iptables rules"

        from net.filtering import create_init_script

        nf = NetworkFilter(mode=NetworkMode.FILTER)
        init_script_path = create_init_script(
            nf,
            ["echo", "test"],
            "/usr/bin/iptables",
            "/usr/bin/ip6tables",
            False,
            "exec setpriv --bounding-set=-net_admin -- {command}",
            use_seccomp=True,
        )

        script_content = init_script_path.read_text()
        assert "exec python3 -c '" in script_content
        assert "SECCOMP_EXEC_CMD" in script_content
        assert "PR_SET_SECCOMP" in script_content

    @patch("net.filtering.find_cap_drop_tool")
    @patch("net.iptables.find_iptables")
    @patch("net.iptables.generate_init_script")
    def test_init_script_excludes_seccomp_when_disabled(
        self, mock_iptables_script, mock_find_iptables, mock_find_cap_drop
    ):
        """Init script should NOT include seccomp when use_seccomp=False."""
        mock_find_iptables.return_value = (
            "/usr/bin/iptables",
            "/usr/bin/ip6tables",
            False,
        )
        mock_find_cap_drop.return_value = (
            "/usr/bin/setpriv",
            "exec setpriv --bounding-set=-net_admin -- {command}",
        )
        mock_iptables_script.return_value = "# iptables rules"

        from net.filtering import create_init_script

        nf = NetworkFilter(mode=NetworkMode.FILTER)
        init_script_path = create_init_script(
            nf,
            ["echo", "test"],
            "/usr/bin/iptables",
            "/usr/bin/ip6tables",
            False,
            "exec setpriv --bounding-set=-net_admin -- {command}",
            use_seccomp=False,
        )

        script_content = init_script_path.read_text()
        assert "SECCOMP_EXEC_CMD" not in script_content


class TestPrepareBwrapCommandWithSeccomp:
    """Tests for prepare_bwrap_command with seccomp option."""

    def test_removes_disable_userns_when_use_seccomp(self):
        """prepare_bwrap_command should remove --disable-userns when use_seccomp=True."""
        from net.pasta_args import prepare_bwrap_command

        cmd = ["bwrap", "--disable-userns", "--unshare-net", "--", "bash"]
        result = prepare_bwrap_command(cmd, "/tmp/test", use_seccomp=True)

        assert "--disable-userns" not in result

    def test_keeps_disable_userns_when_no_seccomp(self):
        """prepare_bwrap_command should keep --disable-userns when use_seccomp=False."""
        from net.pasta_args import prepare_bwrap_command

        cmd = ["bwrap", "--disable-userns", "--unshare-net", "--", "bash"]
        result = prepare_bwrap_command(cmd, "/tmp/test", use_seccomp=False)

        assert "--disable-userns" in result

    def test_still_removes_unshare_net(self):
        """prepare_bwrap_command should still remove --unshare-net regardless."""
        from net.pasta_args import prepare_bwrap_command

        cmd = ["bwrap", "--disable-userns", "--unshare-net", "--", "bash"]

        result_with_seccomp = prepare_bwrap_command(cmd.copy(), "/tmp/test", use_seccomp=True)
        result_without_seccomp = prepare_bwrap_command(cmd.copy(), "/tmp/test", use_seccomp=False)

        assert "--unshare-net" not in result_with_seccomp
        assert "--unshare-net" not in result_without_seccomp
