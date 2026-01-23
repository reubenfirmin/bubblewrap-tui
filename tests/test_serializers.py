"""Tests for model serializers."""

import pytest

from model.serializers import network_to_summary, process_to_summary
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
