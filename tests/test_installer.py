"""Regression coverage for the installed untrusted profile (PR #115)."""

from model import SandboxConfig
from model.network_filter import FilterMode, NetworkMode
from model.serializers import network_to_args
from net.iptables import generate_iptables_rules
from profiles import deserialize, serialize


def test_installed_untrusted_activates_network_filtering(untrusted_config):
    # Loading the installer JSON used to silently discard its network_filter
    # object and default to unrestricted --share-net networking.
    nf = untrusted_config.network_filter
    assert nf.mode == NetworkMode.FILTER
    assert nf.ip_filter.mode == FilterMode.BLACKLIST
    assert nf.requires_pasta()
    assert set(nf.ip_filter.cidrs) == {
        "127.0.0.0/8", "::1/128", "10.0.0.0/8", "172.16.0.0/12",
        "192.168.0.0/16", "169.254.0.0/16", "fe80::/10", "fc00::/7",
    }
    args = network_to_args(untrusted_config._network_group, nf)
    assert "--unshare-net" in args
    assert "--share-net" not in args

    v4, v6 = generate_iptables_rules(nf)
    for cidr in nf.ip_filter.cidrs:
        rules, tool = (v6, "ip6tables") if ":" in cidr else (v4, "iptables")
        assert f"{tool} -A OUTPUT -d {cidr} -j DROP" in rules
    assert not any(rule.endswith("-A OUTPUT -j DROP") for rule in v4 + v6)


def test_untrusted_filter_survives_profile_save_and_reload(untrusted_config):
    restored = deserialize(SandboxConfig, serialize(untrusted_config))
    assert restored.network_filter == untrusted_config.network_filter
    assert restored.network_filter.requires_pasta()
