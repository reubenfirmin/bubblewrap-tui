"""Tests for network filter model."""

import pytest

from model.network_filter import (
    FilterMode,
    HostnameFilter,
    IPFilter,
    NetworkFilter,
    NetworkMode,
    PortForwarding,
)


class TestFilterMode:
    """Test FilterMode enum."""

    def test_values(self):
        """FilterMode has expected values."""
        assert FilterMode.OFF.value == "off"
        assert FilterMode.WHITELIST.value == "whitelist"
        assert FilterMode.BLACKLIST.value == "blacklist"

    def test_from_string(self):
        """FilterMode can be created from string."""
        assert FilterMode("off") == FilterMode.OFF
        assert FilterMode("whitelist") == FilterMode.WHITELIST
        assert FilterMode("blacklist") == FilterMode.BLACKLIST


class TestHostnameFilter:
    """Test HostnameFilter dataclass."""

    def test_defaults(self):
        """HostnameFilter has correct defaults."""
        hf = HostnameFilter()
        assert hf.mode == FilterMode.OFF
        assert hf.hosts == []

    def test_with_hosts(self):
        """HostnameFilter can be created with hosts."""
        hf = HostnameFilter(
            mode=FilterMode.WHITELIST,
            hosts=["github.com", "registry.npmjs.org"],
        )
        assert hf.mode == FilterMode.WHITELIST
        assert len(hf.hosts) == 2
        assert "github.com" in hf.hosts


class TestIPFilter:
    """Test IPFilter dataclass."""

    def test_defaults(self):
        """IPFilter has correct defaults."""
        ipf = IPFilter()
        assert ipf.mode == FilterMode.OFF
        assert ipf.cidrs == []

    def test_with_cidrs(self):
        """IPFilter can be created with CIDRs."""
        ipf = IPFilter(
            mode=FilterMode.BLACKLIST,
            cidrs=["10.0.0.0/8", "192.168.0.0/16"],
        )
        assert ipf.mode == FilterMode.BLACKLIST
        assert len(ipf.cidrs) == 2


class TestPortForwarding:
    """Test PortForwarding dataclass."""

    def test_defaults(self):
        """PortForwarding has correct defaults."""
        pf = PortForwarding()
        assert pf.expose_ports == []
        assert pf.host_ports == []

    def test_with_ports(self):
        """PortForwarding can be created with ports."""
        pf = PortForwarding(
            expose_ports=[8080, 3000],
            host_ports=[5432, 6379],
        )
        assert len(pf.expose_ports) == 2
        assert len(pf.host_ports) == 2
        assert 8080 in pf.expose_ports
        assert 5432 in pf.host_ports


class TestNetworkFilter:
    """Test NetworkFilter dataclass."""

    def test_defaults(self):
        """NetworkFilter has correct defaults."""
        nf = NetworkFilter()
        assert nf.enabled is False
        assert nf.hostname_filter.mode == FilterMode.OFF
        assert nf.ip_filter.mode == FilterMode.OFF
        assert nf.port_forwarding.expose_ports == []
        assert nf.port_forwarding.host_ports == []

    def test_requires_pasta_disabled(self):
        """requires_pasta returns False when mode is OFF."""
        nf = NetworkFilter(mode=NetworkMode.OFF)
        assert nf.requires_pasta() is False

    def test_requires_pasta_enabled_no_rules(self):
        """requires_pasta returns False when filter mode enabled but no rules."""
        nf = NetworkFilter(mode=NetworkMode.FILTER)
        assert nf.requires_pasta() is False

    def test_requires_pasta_with_hostname_filter(self):
        """requires_pasta returns True with hostname filter."""
        nf = NetworkFilter(
            mode=NetworkMode.FILTER,
            hostname_filter=HostnameFilter(
                mode=FilterMode.WHITELIST,
                hosts=["github.com"],
            ),
        )
        assert nf.requires_pasta() is True

    def test_requires_pasta_with_ip_filter(self):
        """requires_pasta returns True with IP filter."""
        nf = NetworkFilter(
            mode=NetworkMode.FILTER,
            ip_filter=IPFilter(
                mode=FilterMode.BLACKLIST,
                cidrs=["10.0.0.0/8"],
            ),
        )
        assert nf.requires_pasta() is True

    def test_requires_pasta_with_ports(self):
        """requires_pasta returns True with port forwarding."""
        nf = NetworkFilter(
            mode=NetworkMode.FILTER,
            port_forwarding=PortForwarding(host_ports=[5432]),
        )
        assert nf.requires_pasta() is True

    def test_requires_pasta_audit_mode(self):
        """requires_pasta returns True in audit mode."""
        nf = NetworkFilter(mode=NetworkMode.AUDIT)
        assert nf.requires_pasta() is True

    def test_is_audit_mode(self):
        """is_audit_mode returns True when mode is AUDIT."""
        nf = NetworkFilter(mode=NetworkMode.AUDIT)
        assert nf.is_audit_mode() is True
        assert nf.is_filter_mode() is False

    def test_is_filter_mode(self):
        """is_filter_mode returns True when mode is FILTER."""
        nf = NetworkFilter(mode=NetworkMode.FILTER)
        assert nf.is_filter_mode() is True
        assert nf.is_audit_mode() is False

    def test_enabled_property_backwards_compat(self):
        """enabled property works for backwards compatibility."""
        nf = NetworkFilter()
        assert nf.enabled is False
        nf.enabled = True
        assert nf.mode == NetworkMode.FILTER
        nf.enabled = False
        assert nf.mode == NetworkMode.OFF

    def test_has_any_rules_false(self):
        """has_any_rules returns False when no filters active."""
        nf = NetworkFilter()
        assert nf.has_any_rules() is False

    def test_has_any_rules_hostname(self):
        """has_any_rules returns True with hostname filter."""
        nf = NetworkFilter(
            hostname_filter=HostnameFilter(mode=FilterMode.WHITELIST),
        )
        assert nf.has_any_rules() is True

    def test_has_any_rules_ip(self):
        """has_any_rules returns True with IP filter."""
        nf = NetworkFilter(
            ip_filter=IPFilter(mode=FilterMode.BLACKLIST),
        )
        assert nf.has_any_rules() is True

    def test_has_port_forwards_false(self):
        """has_port_forwards returns False when no ports."""
        nf = NetworkFilter()
        assert nf.has_port_forwards() is False

    def test_has_port_forwards_true(self):
        """has_port_forwards returns True with ports."""
        # Test with host ports
        nf = NetworkFilter(
            port_forwarding=PortForwarding(host_ports=[5432]),
        )
        assert nf.has_port_forwards() is True
        # Test with expose ports
        nf2 = NetworkFilter(
            port_forwarding=PortForwarding(expose_ports=[8080]),
        )
        assert nf2.has_port_forwards() is True
