"""Tests for net module utilities."""

from unittest.mock import patch, MagicMock

import pytest

from model.network_filter import (
    FilterMode,
    HostnameFilter,
    IPFilter,
    NetworkFilter,
    PortForwarding,
)
from net import (
    HostnameResolutionError,
    check_pasta,
    generate_iptables_rules,
    generate_init_script,
    generate_pasta_args,
    get_install_instructions,
    get_pasta_status,
    get_www_variant,
    is_ipv6,
    resolve_hostname,
    validate_cidr,
    validate_port,
)


class TestCheckPasta:
    """Test check_pasta function."""

    def test_returns_bool(self):
        """check_pasta returns a boolean."""
        result = check_pasta()
        assert isinstance(result, bool)

    @patch("shutil.which")
    def test_returns_true_when_installed(self, mock_which):
        """check_pasta returns True when installed."""
        mock_which.return_value = "/usr/bin/pasta"
        assert check_pasta() is True

    @patch("shutil.which")
    def test_returns_false_when_not_installed(self, mock_which):
        """check_pasta returns False when not installed."""
        mock_which.return_value = None
        assert check_pasta() is False


class TestGetInstallInstructions:
    """Test get_install_instructions function."""

    def test_returns_string(self):
        """get_install_instructions returns a string."""
        result = get_install_instructions()
        assert isinstance(result, str)
        assert "passt" in result


class TestIsIPv6:
    """Test is_ipv6 function."""

    def test_ipv4_address(self):
        """IPv4 address is not IPv6."""
        assert is_ipv6("192.168.1.1") is False

    def test_ipv4_cidr(self):
        """IPv4 CIDR is not IPv6."""
        assert is_ipv6("10.0.0.0/8") is False

    def test_ipv6_address(self):
        """IPv6 address is IPv6."""
        assert is_ipv6("2001:db8::1") is True

    def test_ipv6_cidr(self):
        """IPv6 CIDR is IPv6."""
        assert is_ipv6("2001:db8::/32") is True

    def test_invalid_returns_false(self):
        """Invalid address returns False."""
        assert is_ipv6("not an ip") is False


class TestValidateCidr:
    """Test validate_cidr function."""

    def test_valid_ipv4(self):
        """Valid IPv4 address is valid."""
        assert validate_cidr("192.168.1.1") is True

    def test_valid_ipv4_cidr(self):
        """Valid IPv4 CIDR is valid."""
        assert validate_cidr("10.0.0.0/8") is True

    def test_valid_ipv6(self):
        """Valid IPv6 address is valid."""
        assert validate_cidr("2001:db8::1") is True

    def test_valid_ipv6_cidr(self):
        """Valid IPv6 CIDR is valid."""
        assert validate_cidr("2001:db8::/32") is True

    def test_invalid(self):
        """Invalid address is invalid."""
        assert validate_cidr("not an ip") is False
        assert validate_cidr("256.1.1.1") is False


class TestValidatePort:
    """Test validate_port function."""

    def test_valid_int(self):
        """Valid port as int is valid."""
        assert validate_port(80) is True
        assert validate_port(443) is True
        assert validate_port(5432) is True

    def test_valid_string(self):
        """Valid port as string is valid."""
        assert validate_port("80") is True
        assert validate_port("443") is True

    def test_edge_cases(self):
        """Edge case ports."""
        assert validate_port(1) is True
        assert validate_port(65535) is True

    def test_invalid(self):
        """Invalid ports."""
        assert validate_port(0) is False
        assert validate_port(65536) is False
        assert validate_port(-1) is False
        assert validate_port("not a port") is False


class TestGetWwwVariant:
    """Test get_www_variant function."""

    def test_adds_www_to_bare_domain(self):
        """Bare domain gets www. prefix."""
        assert get_www_variant("github.com") == "www.github.com"
        assert get_www_variant("example.org") == "www.example.org"

    def test_strips_www_from_www_domain(self):
        """www. domain gets stripped."""
        assert get_www_variant("www.github.com") == "github.com"
        assert get_www_variant("www.example.org") == "example.org"

    def test_returns_none_for_invalid(self):
        """Invalid hostnames return None."""
        assert get_www_variant("localhost") is None  # No dot
        assert get_www_variant("") is None


class TestResolveHostname:
    """Test resolve_hostname function."""

    @patch("socket.getaddrinfo")
    def test_returns_ipv4_and_ipv6(self, mock_getaddrinfo):
        """resolve_hostname returns both IPv4 and IPv6."""
        import socket
        mock_getaddrinfo.return_value = [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0)),
            (socket.AF_INET6, socket.SOCK_STREAM, 6, "", ("2606:2800:220:1:248:1893:25c8:1946", 0, 0, 0)),
        ]
        ipv4, ipv6 = resolve_hostname("example.com")
        assert "93.184.216.34" in ipv4
        assert "2606:2800:220:1:248:1893:25c8:1946" in ipv6

    @patch("socket.getaddrinfo")
    def test_raises_on_resolution_failure(self, mock_getaddrinfo):
        """resolve_hostname raises HostnameResolutionError on failure."""
        import socket

        mock_getaddrinfo.side_effect = socket.gaierror("Name resolution failed")
        with pytest.raises(HostnameResolutionError) as exc_info:
            resolve_hostname("nonexistent.invalid")
        assert "nonexistent.invalid" in str(exc_info.value)


class TestGenerateIptablesRules:
    """Test generate_iptables_rules function."""

    def test_basic_rules_always_present(self):
        """Basic loopback rules are always present."""
        nf = NetworkFilter()
        v4, v6 = generate_iptables_rules(nf)
        # Loopback rules
        assert any("-o lo" in r for r in v4)
        assert any("-i lo" in r for r in v4)

    def test_whitelist_adds_drop_all(self):
        """Whitelist mode adds DROP rule at end."""
        nf = NetworkFilter(
            ip_filter=IPFilter(
                mode=FilterMode.WHITELIST,
                cidrs=["10.0.0.0/8"],
            ),
        )
        v4, v6 = generate_iptables_rules(nf)
        # Should have DROP rule
        assert any("-j DROP" in r and "-d" not in r for r in v4)

    def test_blacklist_does_not_add_drop_all(self):
        """Blacklist mode doesn't add final DROP rule."""
        nf = NetworkFilter(
            ip_filter=IPFilter(
                mode=FilterMode.BLACKLIST,
                cidrs=["10.0.0.0/8"],
            ),
        )
        v4, v6 = generate_iptables_rules(nf)
        # Should have DROP rule for the CIDR, but not catch-all DROP
        drop_rules = [r for r in v4 if "-j DROP" in r]
        assert all("-d" in r for r in drop_rules)

    def test_whitelist_ip_adds_accept(self):
        """Whitelist IP adds ACCEPT rule."""
        nf = NetworkFilter(
            ip_filter=IPFilter(
                mode=FilterMode.WHITELIST,
                cidrs=["10.0.0.0/8"],
            ),
        )
        v4, v6 = generate_iptables_rules(nf)
        assert any("-d 10.0.0.0/8 -j ACCEPT" in r for r in v4)

    def test_blacklist_ip_adds_drop(self):
        """Blacklist IP adds DROP rule."""
        nf = NetworkFilter(
            ip_filter=IPFilter(
                mode=FilterMode.BLACKLIST,
                cidrs=["192.168.1.0/24"],
            ),
        )
        v4, v6 = generate_iptables_rules(nf)
        assert any("-d 192.168.1.0/24 -j DROP" in r for r in v4)

    def test_ipv6_rules_generated(self):
        """IPv6 rules are generated for IPv6 CIDRs."""
        nf = NetworkFilter(
            ip_filter=IPFilter(
                mode=FilterMode.WHITELIST,
                cidrs=["2001:db8::/32"],
            ),
        )
        v4, v6 = generate_iptables_rules(nf)
        assert any("2001:db8::/32" in r for r in v6)

    def test_hostname_filtering_uses_dns_proxy(self):
        """Hostname filtering uses DNS proxy, not iptables IP rules."""
        # With DNS proxy active, hostname filtering is handled at DNS layer
        # so no IP-based iptables rules should be generated for hostnames
        nf = NetworkFilter(
            hostname_filter=HostnameFilter(
                mode=FilterMode.WHITELIST,
                hosts=["example.com"],
            ),
        )
        v4, v6 = generate_iptables_rules(nf)
        # DNS proxy handles filtering, so no hostname IPs in iptables
        # Only loopback/established rules should exist
        assert not any("93.184.216.34" in r for r in v4)
        # Should have basic rules (loopback, DNS)
        assert any("lo" in r for r in v4)


class TestGenerateInitScript:
    """Test generate_init_script function."""

    def test_returns_shell_script(self):
        """generate_init_script returns a shell script."""
        nf = NetworkFilter(
            ip_filter=IPFilter(
                mode=FilterMode.WHITELIST,
                cidrs=["10.0.0.0/8"],
            ),
        )
        script = generate_init_script(nf, "/usr/bin/iptables", "/usr/bin/ip6tables", is_multicall=False)
        assert "/usr/bin/iptables" in script

    def test_includes_ipv6_rules(self):
        """Script includes ip6tables rules."""
        nf = NetworkFilter(
            ip_filter=IPFilter(
                mode=FilterMode.WHITELIST,
                cidrs=["2001:db8::/32"],
            ),
        )
        script = generate_init_script(nf, "/usr/bin/iptables", "/usr/bin/ip6tables", is_multicall=False)
        assert "/usr/bin/ip6tables" in script

    def test_multicall_binary_invocation(self):
        """Multi-call binary is invoked correctly."""
        nf = NetworkFilter(
            ip_filter=IPFilter(
                mode=FilterMode.WHITELIST,
                cidrs=["10.0.0.0/8"],
            ),
        )
        script = generate_init_script(nf, "/usr/bin/xtables-nft-multi", "/usr/bin/xtables-nft-multi", is_multicall=True)
        assert "/usr/bin/xtables-nft-multi iptables" in script
        assert "/usr/bin/xtables-nft-multi ip6tables" in script


class TestGeneratePastaArgs:
    """Test generate_pasta_args function."""

    def test_basic_args(self):
        """generate_pasta_args returns basic arguments for spawn mode."""
        nf = NetworkFilter()
        args = generate_pasta_args(nf)
        assert args[0] == "pasta"
        assert "--config-net" in args
        assert "--quiet" in args
        # Spawn mode doesn't use --netns
        assert "--netns" not in args

    def test_port_forwarding(self):
        """Port forwards are included with -t and -T flags."""
        nf = NetworkFilter(
            port_forwarding=PortForwarding(
                expose_ports=[8080],
                host_ports=[5432, 6379],
            ),
        )
        args = generate_pasta_args(nf)
        # Expose ports use -t
        assert "-t" in args
        assert "8080" in args
        # Host ports use -T
        assert "-T" in args
        assert "5432" in args
        assert "6379" in args

    def test_no_ports_no_T_flag(self):
        """No -T flag when no ports configured."""
        nf = NetworkFilter()
        args = generate_pasta_args(nf)
        assert "-T" not in args


class TestGetPastaStatus:
    """Test get_pasta_status function."""

    @patch("net.pasta_install.check_pasta")
    def test_installed(self, mock_check):
        """Returns installed status when installed."""
        mock_check.return_value = True
        installed, message = get_pasta_status()
        assert installed is True
        assert "installed" in message

    @patch("net.pasta_install.check_pasta")
    @patch("net.pasta_install.get_install_instructions")
    def test_not_installed(self, mock_instructions, mock_check):
        """Returns install instructions when not installed."""
        mock_check.return_value = False
        mock_instructions.return_value = "sudo apt install passt"
        installed, message = get_pasta_status()
        assert installed is False
        assert "apt" in message


class TestIptablesRuleOrdering:
    """Test iptables rule ordering for correct filtering behavior.

    Rule ordering is critical for iptables. Rules are processed in order,
    and the first matching rule wins. These tests verify that:
    1. DROP rules come before general ACCEPT rules for blocked addresses
    2. DNS port 53 exceptions come before DROP rules
    3. Loopback accept is conditional on not blocking loopback
    """

    def test_loopback_drop_before_loopback_accept(self):
        """When blocking 127.0.0.0/8, DROP must come before any loopback ACCEPT.

        This is the key fix for the 'ping localhost' bug where the order was wrong.
        """
        nf = NetworkFilter(
            ip_filter=IPFilter(
                mode=FilterMode.BLACKLIST,
                cidrs=["127.0.0.0/8"],
            ),
        )
        v4, v6 = generate_iptables_rules(nf)

        # Find the DROP rule for 127.0.0.0/8
        drop_idx = None
        for i, rule in enumerate(v4):
            if "-d 127.0.0.0/8" in rule and "-j DROP" in rule:
                drop_idx = i
                break

        # Find any general loopback OUTPUT accept
        loopback_accept_idx = None
        for i, rule in enumerate(v4):
            if "-o lo" in rule and "-j ACCEPT" in rule and "--dport" not in rule:
                loopback_accept_idx = i
                break

        # DROP must exist
        assert drop_idx is not None, "DROP rule for 127.0.0.0/8 should exist"

        # If there's a general loopback accept, it must come AFTER the DROP
        # (But actually, when blocking loopback, there should be NO general accept)
        if loopback_accept_idx is not None:
            assert drop_idx < loopback_accept_idx, \
                "DROP 127.0.0.0/8 must come before general loopback ACCEPT"

    def test_no_general_loopback_accept_when_blocking_loopback(self):
        """When blocking 127.0.0.0/8, no general loopback OUTPUT accept should exist."""
        nf = NetworkFilter(
            ip_filter=IPFilter(
                mode=FilterMode.BLACKLIST,
                cidrs=["127.0.0.0/8"],
            ),
        )
        v4, v6 = generate_iptables_rules(nf)

        # Should NOT have a general loopback OUTPUT accept (without port restriction)
        general_loopback_accepts = [
            r for r in v4
            if "-o lo" in r and "-j ACCEPT" in r and "--dport" not in r
        ]
        assert len(general_loopback_accepts) == 0, \
            "No general loopback ACCEPT when blocking 127.0.0.0/8"

    def test_loopback_input_always_allowed(self):
        """Loopback INPUT is always allowed (for responses)."""
        nf = NetworkFilter(
            ip_filter=IPFilter(
                mode=FilterMode.BLACKLIST,
                cidrs=["127.0.0.0/8"],
            ),
        )
        v4, v6 = generate_iptables_rules(nf)

        # INPUT -i lo should always be present
        input_rules = [r for r in v4 if "-i lo" in r and "-j ACCEPT" in r]
        assert len(input_rules) > 0, "Loopback INPUT accept should always exist"

    def test_dns_port_53_before_loopback_drop_when_dns_proxy(self):
        """DNS port 53 rules come before loopback DROP when DNS proxy is active."""
        nf = NetworkFilter(
            ip_filter=IPFilter(
                mode=FilterMode.BLACKLIST,
                cidrs=["127.0.0.0/8"],
            ),
            hostname_filter=HostnameFilter(
                mode=FilterMode.WHITELIST,  # Triggers DNS proxy
                hosts=["example.com"],
            ),
        )
        v4, v6 = generate_iptables_rules(nf)

        # Find DNS port 53 rule
        dns_idx = None
        for i, rule in enumerate(v4):
            if "--dport 53" in rule and "-j ACCEPT" in rule:
                dns_idx = i
                break

        # Find DROP rule for 127.0.0.0/8
        drop_idx = None
        for i, rule in enumerate(v4):
            if "-d 127.0.0.0/8" in rule and "-j DROP" in rule:
                drop_idx = i
                break

        assert dns_idx is not None, "DNS port 53 rule should exist when DNS proxy active"
        assert drop_idx is not None, "DROP rule should exist"
        assert dns_idx < drop_idx, "DNS port 53 ACCEPT must come before loopback DROP"

    def test_ipv6_loopback_drop_before_accept(self):
        """IPv6 ::1/128 DROP must come before general loopback accept."""
        nf = NetworkFilter(
            ip_filter=IPFilter(
                mode=FilterMode.BLACKLIST,
                cidrs=["::1/128"],
            ),
        )
        v4, v6 = generate_iptables_rules(nf)

        # Should NOT have general loopback OUTPUT accept for IPv6
        general_loopback_accepts = [
            r for r in v6
            if "-o lo" in r and "-j ACCEPT" in r and "--dport" not in r
        ]
        assert len(general_loopback_accepts) == 0, \
            "No general loopback ACCEPT when blocking ::1/128"

    def test_multiple_blacklist_cidrs_all_before_loopback_accept(self):
        """All blacklist DROP rules come before any general loopback accept."""
        nf = NetworkFilter(
            ip_filter=IPFilter(
                mode=FilterMode.BLACKLIST,
                cidrs=["10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"],
            ),
        )
        v4, v6 = generate_iptables_rules(nf)

        # Find all DROP rules
        drop_indices = [
            i for i, rule in enumerate(v4)
            if "-j DROP" in rule and "-d" in rule
        ]

        # Find general loopback accept
        loopback_accept_idx = None
        for i, rule in enumerate(v4):
            if "-o lo" in rule and "-j ACCEPT" in rule and "--dport" not in rule:
                loopback_accept_idx = i
                break

        # All DROP rules should come before loopback accept (if it exists)
        if loopback_accept_idx is not None:
            for drop_idx in drop_indices:
                assert drop_idx < loopback_accept_idx, \
                    f"DROP rule at {drop_idx} should come before loopback ACCEPT at {loopback_accept_idx}"

    def test_whitelist_mode_drop_all_at_end(self):
        """Whitelist mode has DROP all at the end."""
        nf = NetworkFilter(
            ip_filter=IPFilter(
                mode=FilterMode.WHITELIST,
                cidrs=["8.8.8.8"],
            ),
        )
        v4, v6 = generate_iptables_rules(nf)

        # Last rule should be DROP all (no -d)
        drop_all_rules = [r for r in v4 if "-j DROP" in r and "-d" not in r]
        assert len(drop_all_rules) > 0, "Whitelist mode should have DROP all"

        # It should be at the end
        last_rule = v4[-1]
        assert "-j DROP" in last_rule and "-d" not in last_rule, \
            "DROP all should be the last rule"

    def test_blacklist_with_loopback_has_correct_rule_sequence(self):
        """Full test of rule sequence when blocking loopback."""
        nf = NetworkFilter(
            ip_filter=IPFilter(
                mode=FilterMode.BLACKLIST,
                cidrs=["127.0.0.0/8", "10.0.0.0/8"],
            ),
        )
        v4, v6 = generate_iptables_rules(nf)

        # Expected sequence:
        # 1. INPUT -i lo -j ACCEPT (always first for responses)
        # 2. DROP rules for blacklisted CIDRs
        # 3. NO general loopback OUTPUT accept (because 127.0.0.0/8 is blocked)

        # First rule should be INPUT loopback accept
        assert "-i lo" in v4[0] and "INPUT" in v4[0]

        # Should have DROP for 127.0.0.0/8
        assert any("-d 127.0.0.0/8 -j DROP" in r for r in v4)

        # Should have DROP for 10.0.0.0/8
        assert any("-d 10.0.0.0/8 -j DROP" in r for r in v4)

        # Should NOT have general OUTPUT loopback accept
        general_lo_accept = [
            r for r in v4
            if "OUTPUT" in r and "-o lo" in r and "-j ACCEPT" in r and "--dport" not in r
        ]
        assert len(general_lo_accept) == 0

    def test_non_loopback_blacklist_allows_loopback(self):
        """Blacklist that doesn't include loopback should allow loopback."""
        nf = NetworkFilter(
            ip_filter=IPFilter(
                mode=FilterMode.BLACKLIST,
                cidrs=["10.0.0.0/8", "192.168.0.0/16"],  # No 127.x.x.x
            ),
        )
        v4, v6 = generate_iptables_rules(nf)

        # Should have general loopback OUTPUT accept
        general_lo_accept = [
            r for r in v4
            if "-o lo" in r and "-j ACCEPT" in r and "--dport" not in r
        ]
        assert len(general_lo_accept) > 0, \
            "Should have loopback accept when not blocking loopback"

    def test_partial_loopback_block_still_blocks(self):
        """Blocking 127.0.0.1 (not /8) should still prevent general loopback accept."""
        nf = NetworkFilter(
            ip_filter=IPFilter(
                mode=FilterMode.BLACKLIST,
                cidrs=["127.0.0.1"],
            ),
        )
        v4, v6 = generate_iptables_rules(nf)

        # Should NOT have general loopback OUTPUT accept
        general_lo_accept = [
            r for r in v4
            if "-o lo" in r and "-j ACCEPT" in r and "--dport" not in r
        ]
        assert len(general_lo_accept) == 0, \
            "No general loopback accept when blocking any 127.x.x.x"
