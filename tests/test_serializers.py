"""Tests for model serializers."""

import pytest

from model.serializers import isolation_to_args, isolation_to_summary, network_to_summary, process_to_summary
from model.config_group import ConfigGroup
from model.network_filter import NetworkFilter, NetworkMode, FilterMode


class TestProcessToSummary:
    """Tests for process_to_summary function."""

    def _make_process_group(self, **kwargs) -> ConfigGroup:
        """Create a process group with given settings."""
        group = ConfigGroup(name="process", title="Process", items=[])
        for key, value in kwargs.items():
            group.set(key, value)
        return group

    def _make_isolation_group(self, **kwargs) -> ConfigGroup:
        """Create an isolation group with given settings."""
        group = ConfigGroup(name="isolation", title="Isolation", items=[])
        for key, value in kwargs.items():
            group.set(key, value)
        return group

    def _make_env_group(self) -> ConfigGroup:
        """Create a minimal environment group."""
        return ConfigGroup(name="env", title="Environment", items=[])

    def test_as_pid_1_shows_auto_enabled_when_unshare_pid_false(self):
        """When as_pid_1 is set and unshare_pid is not, summary should indicate auto-enabled."""
        process_group = self._make_process_group(as_pid_1=True)
        isolation_group = self._make_isolation_group(unshare_pid=False)
        env_group = self._make_env_group()

        summary = process_to_summary(process_group, env_group, isolation_group)

        assert summary is not None
        assert "PID namespace auto-enabled" in summary

    def test_as_pid_1_no_auto_text_when_unshare_pid_true(self):
        """When as_pid_1 is set and unshare_pid is already true, no auto-enabled text."""
        process_group = self._make_process_group(as_pid_1=True)
        isolation_group = self._make_isolation_group(unshare_pid=True)
        env_group = self._make_env_group()

        summary = process_to_summary(process_group, env_group, isolation_group)

        assert summary is not None
        assert "auto-enabled" not in summary
        assert "PID 1" in summary

    def test_as_pid_1_without_isolation_group(self):
        """When isolation_group is None, should not crash."""
        process_group = self._make_process_group(as_pid_1=True)
        env_group = self._make_env_group()

        summary = process_to_summary(process_group, env_group, None)

        assert summary is not None
        assert "PID 1" in summary

    def test_die_with_parent(self):
        """die_with_parent shows lifecycle message."""
        process_group = self._make_process_group(die_with_parent=True)
        env_group = self._make_env_group()

        summary = process_to_summary(process_group, env_group)

        assert summary is not None
        assert "Lifecycle" in summary

    def test_new_session(self):
        """new_session shows session message."""
        process_group = self._make_process_group(new_session=True)
        env_group = self._make_env_group()

        summary = process_to_summary(process_group, env_group)

        assert summary is not None
        assert "Session" in summary

    def test_chdir(self):
        """chdir shows working directory."""
        process_group = self._make_process_group(chdir="/home/user")
        env_group = self._make_env_group()

        summary = process_to_summary(process_group, env_group)

        assert summary is not None
        assert "/home/user" in summary

    def test_empty_returns_none(self):
        """Empty process group returns None."""
        process_group = self._make_process_group()
        env_group = self._make_env_group()

        summary = process_to_summary(process_group, env_group)

        assert summary is None


class TestNetworkToSummary:
    """Tests for network_to_summary function."""

    def _make_network_group(self, **kwargs) -> ConfigGroup:
        """Create a network group with given settings."""
        group = ConfigGroup(name="network", title="Network", items=[])
        for key, value in kwargs.items():
            group.set(key, value)
        return group

    def test_share_net_full_access(self):
        """share_net shows full access."""
        group = self._make_network_group(share_net=True, bind_resolv_conf=True)

        summary = network_to_summary(group)

        assert summary is not None
        assert "Full access" in summary

    def test_share_net_with_dns_and_ssl(self):
        """share_net with DNS and SSL shows both."""
        group = self._make_network_group(
            share_net=True, bind_resolv_conf=True, bind_ssl_certs=True
        )

        summary = network_to_summary(group)

        assert summary is not None
        assert "DNS config" in summary
        assert "SSL certs" in summary

    def test_share_net_without_extras_shows_warning(self):
        """share_net without DNS/SSL shows warning."""
        group = self._make_network_group(share_net=True)

        summary = network_to_summary(group)

        assert summary is not None
        assert "WARNING" in summary

    def test_offline_when_no_network(self):
        """Without share_net or filtering, shows offline."""
        group = self._make_network_group(share_net=False)

        summary = network_to_summary(group, None)

        assert summary is not None
        assert "offline" in summary.lower()

    def test_filtered_access_with_pasta(self):
        """When network_filter requires pasta, shows filtered access."""
        group = self._make_network_group(share_net=False)
        nf = NetworkFilter()
        nf.mode = NetworkMode.FILTER
        nf.hostname_filter.mode = FilterMode.WHITELIST
        nf.hostname_filter.hosts = ["example.com"]

        summary = network_to_summary(group, nf)

        assert summary is not None
        assert "Filtered access" in summary
        assert "pasta" in summary

    def test_offline_with_empty_filter(self):
        """When network_filter doesn't require pasta, shows offline."""
        group = self._make_network_group(share_net=False)
        nf = NetworkFilter()
        nf.mode = NetworkMode.OFF  # Not filter mode

        summary = network_to_summary(group, nf)

        assert summary is not None
        assert "offline" in summary.lower()


class TestNetworkFilterSummary:
    """Tests for NetworkFilter.get_filtering_summary method."""

    def test_empty_whitelist_shows_blocks_all(self):
        """Empty hostname whitelist shows 'blocks all'."""
        nf = NetworkFilter()
        nf.hostname_filter.mode = FilterMode.WHITELIST
        nf.hostname_filter.hosts = []

        summary = nf.get_filtering_summary()

        assert len(summary) == 1
        assert "blocks all" in summary[0]

    def test_empty_blacklist_shows_no_effect(self):
        """Empty hostname blacklist shows 'no effect'."""
        nf = NetworkFilter()
        nf.hostname_filter.mode = FilterMode.BLACKLIST
        nf.hostname_filter.hosts = []

        summary = nf.get_filtering_summary()

        assert len(summary) == 1
        assert "no effect" in summary[0]

    def test_empty_ip_whitelist_shows_blocks_all(self):
        """Empty IP whitelist shows 'blocks all'."""
        nf = NetworkFilter()
        nf.ip_filter.mode = FilterMode.WHITELIST
        nf.ip_filter.cidrs = []

        summary = nf.get_filtering_summary()

        assert len(summary) == 1
        assert "blocks all" in summary[0]

    def test_empty_ip_blacklist_shows_no_effect(self):
        """Empty IP blacklist shows 'no effect'."""
        nf = NetworkFilter()
        nf.ip_filter.mode = FilterMode.BLACKLIST
        nf.ip_filter.cidrs = []

        summary = nf.get_filtering_summary()

        assert len(summary) == 1
        assert "no effect" in summary[0]

    def test_populated_whitelist_shows_hosts(self):
        """Populated hostname whitelist shows the hosts."""
        nf = NetworkFilter()
        nf.hostname_filter.mode = FilterMode.WHITELIST
        nf.hostname_filter.hosts = ["example.com", "test.org"]

        summary = nf.get_filtering_summary()

        assert len(summary) == 1
        assert "example.com" in summary[0]
        assert "test.org" in summary[0]
        assert "blocks all" not in summary[0]


class TestIsolationToArgs:
    """Tests for isolation_to_args — ensures seccomp flags are NOT emitted as placeholders."""

    def _make_isolation_group(self, **kwargs) -> ConfigGroup:
        """Create an isolation group with real field items."""
        from model.fields.isolation import (
            unshare_pid, unshare_ipc, unshare_cgroup,
            disable_userns, enable_seccomp, seccomp_strict,
        )
        group = ConfigGroup(
            name="isolation",
            title="Isolation",
            items=[unshare_pid, unshare_ipc, unshare_cgroup,
                   disable_userns, enable_seccomp, seccomp_strict],
        )
        for key, value in kwargs.items():
            group.set(key, value)
        return group

    def test_seccomp_enabled_does_not_emit_seccomp_flag(self):
        """enable_seccomp should NOT produce --seccomp in serialized args (handled at exec time)."""
        group = self._make_isolation_group(enable_seccomp=True)

        args = isolation_to_args(group)

        assert "--seccomp" not in args

    def test_seccomp_strict_does_not_emit_seccomp_flag(self):
        """seccomp_strict should NOT produce --seccomp in serialized args."""
        group = self._make_isolation_group(seccomp_strict=True)

        args = isolation_to_args(group)

        assert "--seccomp" not in args

    def test_both_seccomp_options_do_not_emit_seccomp_flag(self):
        """Both seccomp options enabled should NOT produce --seccomp."""
        group = self._make_isolation_group(enable_seccomp=True, seccomp_strict=True)

        args = isolation_to_args(group)

        assert "--seccomp" not in args

    def test_no_fd_placeholder_in_args(self):
        """Seccomp args should never contain the '<fd>' placeholder string."""
        group = self._make_isolation_group(enable_seccomp=True, seccomp_strict=True)

        args = isolation_to_args(group)

        assert "<fd>" not in args

    def test_namespace_flags_still_emitted(self):
        """Non-seccomp bwrap_flag items should still be serialized."""
        group = self._make_isolation_group(
            unshare_pid=True, unshare_ipc=True, unshare_cgroup=True,
        )

        args = isolation_to_args(group)

        assert "--unshare-pid" in args
        assert "--unshare-ipc" in args
        assert "--unshare-cgroup" in args

    def test_disable_userns_emitted(self):
        """disable_userns has a bwrap_flag and should be serialized."""
        group = self._make_isolation_group(disable_userns=True)

        args = isolation_to_args(group)

        assert "--disable-userns" in args

    def test_namespace_flags_with_seccomp_no_seccomp_flag(self):
        """Namespace flags emitted alongside seccomp, but no --seccomp flag."""
        group = self._make_isolation_group(
            unshare_pid=True, enable_seccomp=True, seccomp_strict=True,
        )

        args = isolation_to_args(group)

        assert "--unshare-pid" in args
        assert "--seccomp" not in args
        assert "<fd>" not in args

    def test_empty_group_returns_empty_args(self):
        """No options enabled should produce empty args."""
        group = self._make_isolation_group(
            unshare_pid=False, unshare_ipc=False, unshare_cgroup=False,
            disable_userns=False, enable_seccomp=False, seccomp_strict=False,
        )

        args = isolation_to_args(group)

        assert args == []


class TestIsolationToSummary:
    """Tests for isolation_to_summary — seccomp shows in summary text."""

    def _make_isolation_group(self, **kwargs) -> ConfigGroup:
        """Create an isolation group with real field items."""
        from model.fields.isolation import (
            unshare_pid, unshare_ipc, unshare_cgroup,
            disable_userns, enable_seccomp, seccomp_strict,
        )
        group = ConfigGroup(
            name="isolation",
            title="Isolation",
            items=[unshare_pid, unshare_ipc, unshare_cgroup,
                   disable_userns, enable_seccomp, seccomp_strict],
        )
        for key, value in kwargs.items():
            group.set(key, value)
        return group

    def test_seccomp_enabled_shows_in_summary(self):
        """enable_seccomp should appear in the summary text."""
        group = self._make_isolation_group(enable_seccomp=True)

        summary = isolation_to_summary(group)

        assert summary is not None
        assert "seccomp" in summary.lower()

    def test_seccomp_strict_shows_in_summary(self):
        """seccomp_strict should appear in the summary text."""
        group = self._make_isolation_group(seccomp_strict=True)

        summary = isolation_to_summary(group)

        assert summary is not None
        assert "io_uring" in summary.lower() or "exploit" in summary.lower()

    def test_no_seccomp_no_summary_mention(self):
        """Without seccomp, summary should not mention seccomp."""
        group = self._make_isolation_group(
            enable_seccomp=False, seccomp_strict=False,
            unshare_pid=False, unshare_ipc=False,
            unshare_cgroup=False, disable_userns=False,
        )

        summary = isolation_to_summary(group)

        assert summary is None
