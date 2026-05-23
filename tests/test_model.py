"""Tests for model-level changes in #109: UIField default_factory, ConfigGroup,
network_filter property, and network filter UIFields."""

import copy

import pytest

from model.config_group import ConfigGroup
from model.network_filter import FilterMode, NetworkFilter, NetworkMode, PortForwarding
from model.sandbox_config import SandboxConfig
from model.ui_field import UIField


class TestUIFieldDefaultFactory:
    """Test UIField default_factory for mutable defaults (lists, dicts)."""

    def test_default_factory_returns_independent_copies(self):
        """Each access of a default_factory field returns a separate list."""

        class Config:
            items = UIField(list, None, "items-list", "Items", "Item list", default_factory=list)

        a = Config()
        b = Config()
        a.items.append("x")
        assert b.items == []  # b's list is independent

    def test_default_factory_used_when_no_value_set(self):
        """default_factory creates the value on first access."""

        class Config:
            tags = UIField(list, None, "tags-list", "Tags", "Tag list", default_factory=list)

        c = Config()
        assert c.tags == []
        c.tags.append("hello")
        assert c.tags == ["hello"]

    def test_default_without_factory(self):
        """Fields without default_factory use the static default."""
        field = UIField(bool, False, "opt-test", "Test", "Test field")
        assert field.default_factory is None
        assert field.default is False

    def test_widget_id_attribute(self):
        """widget_id (renamed from checkbox_id) is stored correctly."""
        field = UIField(bool, True, "my-widget", "Label", "Explanation")
        assert field.widget_id == "my-widget"


class TestConfigGroupDefaultFactory:
    """Test ConfigGroup handling of UIField default_factory."""

    def _make_group(self):
        field = UIField(list, None, "items-list", "Items", "Item list", default_factory=list)
        field.name = "items"
        return ConfigGroup(name="test", title="Test", items=[field])

    def test_post_init_creates_list_from_factory(self):
        """__post_init__ uses default_factory for list fields."""
        group = self._make_group()
        assert group._values["items"] == []

    def test_post_init_lists_are_independent(self):
        """Each group gets its own list instance."""
        g1 = self._make_group()
        g2 = self._make_group()
        g1._values["items"].append("x")
        assert g2._values["items"] == []

    def test_reset_to_defaults_uses_factory(self):
        """reset_to_defaults creates a fresh list from factory."""
        group = self._make_group()
        group._values["items"].append("x")
        group._values["items"].append("y")
        group.reset_to_defaults()
        assert group._values["items"] == []

    def test_reset_to_defaults_preserves_list_identity(self):
        """reset_to_defaults clears list in-place to preserve shared references."""
        group = self._make_group()
        old_list = group._values["items"]
        old_list.append("x")
        group.reset_to_defaults()
        # Same object, cleared in-place
        assert group._values["items"] is old_list
        assert old_list == []


class TestNetworkFilterProperty:
    """Test SandboxConfig.network_filter property reconstruction."""

    def test_default_network_filter_is_off(self):
        """Default config has network_mode OFF."""
        config = SandboxConfig()
        nf = config.network_filter
        assert nf.mode == NetworkMode.OFF

    def test_filter_mode_from_group(self):
        """network_filter property reads mode from group values."""
        config = SandboxConfig()
        config._network_group.set("network_mode", "filter")
        nf = config.network_filter
        assert nf.mode == NetworkMode.FILTER

    def test_hostname_filter_from_group(self):
        """network_filter property reads hostname filter from group values."""
        config = SandboxConfig()
        config._network_group.set("hostname_mode", "whitelist")
        config._network_group.set("hostname_hosts", ["github.com"])
        nf = config.network_filter
        assert nf.hostname_filter.mode == FilterMode.WHITELIST
        assert nf.hostname_filter.hosts == ["github.com"]

    def test_ip_filter_from_group(self):
        """network_filter property reads IP filter from group values."""
        config = SandboxConfig()
        config._network_group.set("ip_mode", "blacklist")
        config._network_group.set("ip_cidrs", ["10.0.0.0/8"])
        nf = config.network_filter
        assert nf.ip_filter.mode == FilterMode.BLACKLIST
        assert nf.ip_filter.cidrs == ["10.0.0.0/8"]

    def test_port_forwarding_from_group(self):
        """network_filter property reads port forwarding from group values."""
        config = SandboxConfig()
        config._network_group.set("expose_ports", [8080, 3000])
        config._network_group.set("host_ports", [5432])
        nf = config.network_filter
        assert nf.port_forwarding.expose_ports == [8080, 3000]
        assert nf.port_forwarding.host_ports == [5432]

    def test_requires_pasta_with_port_forwards(self):
        """requires_pasta returns True when ports are configured in filter mode."""
        config = SandboxConfig()
        config._network_group.set("network_mode", "filter")
        config._network_group.set("expose_ports", [5173])
        assert config.network_filter.requires_pasta() is True

    def test_requires_pasta_false_when_off(self):
        """requires_pasta returns False when mode is OFF even with ports."""
        config = SandboxConfig()
        config._network_group.set("network_mode", "off")
        config._network_group.set("expose_ports", [5173])
        assert config.network_filter.requires_pasta() is False

    def test_shared_list_reference(self):
        """Lists in network_filter property share references with group values."""
        config = SandboxConfig()
        config._network_group.set("expose_ports", [8080])
        nf = config.network_filter
        # The property reconstructs, so each call creates a new NetworkFilter
        # but the lists should be the same objects (shared reference)
        assert nf.port_forwarding.expose_ports is config._network_group._values["expose_ports"]


class TestNetworkFilterFields:
    """Test that network filter UIFields are correctly defined in the network group."""

    def test_network_group_has_filter_fields(self):
        """Network group includes network_mode, hostname, IP, and port fields."""
        from model.groups import network_group
        field_names = [item.name for item in network_group.items]
        assert "network_mode" in field_names
        assert "hostname_mode" in field_names
        assert "hostname_hosts" in field_names
        assert "ip_mode" in field_names
        assert "ip_cidrs" in field_names
        assert "expose_ports" in field_names
        assert "host_ports" in field_names

    def test_network_mode_default(self):
        """network_mode defaults to 'off' in group values."""
        config = SandboxConfig()
        assert config._network_group._values.get("network_mode") == "off"

    def test_network_mode_reset_to_defaults(self):
        """reset_to_defaults resets network_mode since it's now a UIField item."""
        config = SandboxConfig()
        config._network_group.set("network_mode", "filter")
        config._network_group.reset_to_defaults()
        assert config._network_group._values["network_mode"] == "off"

    def test_list_fields_are_independent_across_configs(self):
        """Each SandboxConfig gets independent list copies for network fields."""
        c1 = SandboxConfig()
        c2 = SandboxConfig()
        c1._network_group._values["expose_ports"].append(8080)
        assert c2._network_group._values["expose_ports"] == []


class TestProfileLoadPreservesListReferences:
    """Test that _restore_group_values mutates lists in-place (Bug #1 fix)."""

    def test_restore_preserves_list_identity(self):
        """After profile restore, the list object in _values is the same instance."""
        from profiles import _restore_group_values

        config = SandboxConfig()
        original_list = config._network_group._values["hostname_hosts"]

        # Simulate profile data with new hostnames
        data = {
            "_network_group": {
                "_values": {
                    "hostname_hosts": ["github.com", "example.com"],
                }
            }
        }
        _restore_group_values(config, data)

        # The list should be the SAME object, mutated in-place
        assert config._network_group._values["hostname_hosts"] is original_list
        assert original_list == ["github.com", "example.com"]

    def test_restore_preserves_port_list_identity(self):
        """Port lists are also preserved in-place."""
        from profiles import _restore_group_values

        config = SandboxConfig()
        original_ports = config._network_group._values["expose_ports"]

        data = {
            "_network_group": {
                "_values": {
                    "expose_ports": [8080, 3000],
                }
            }
        }
        _restore_group_values(config, data)

        assert config._network_group._values["expose_ports"] is original_ports
        assert original_ports == [8080, 3000]

    def test_restore_clears_old_values(self):
        """In-place mutation clears previous values before adding new ones."""
        from profiles import _restore_group_values

        config = SandboxConfig()
        config._network_group._values["hostname_hosts"].extend(["old.com", "stale.com"])

        data = {
            "_network_group": {
                "_values": {
                    "hostname_hosts": ["new.com"],
                }
            }
        }
        _restore_group_values(config, data)

        assert config._network_group._values["hostname_hosts"] == ["new.com"]

    def test_non_list_values_still_replaced(self):
        """Non-list values (strings, bools) are still replaced normally."""
        from profiles import _restore_group_values

        config = SandboxConfig()
        data = {
            "_network_group": {
                "_values": {
                    "network_mode": "filter",
                    "share_net": False,
                }
            }
        }
        _restore_group_values(config, data)

        assert config._network_group._values["network_mode"] == "filter"
        assert config._network_group._values["share_net"] is False
