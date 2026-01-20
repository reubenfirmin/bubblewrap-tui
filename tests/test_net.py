"""Tests for net module utilities."""

from unittest.mock import patch, MagicMock

import pytest

from model.network_filter import (
    FilterMode,
    HostnameFilter,
    IPFilter,
    LocalhostAccess,
    NetworkFilter,
)
from net import (
    check_pasta,
    detect_distro,
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


class TestDetectDistro:
    """Test detect_distro function."""

    @patch("pathlib.Path.exists")
    def test_returns_none_when_no_os_release(self, mock_exists):
        """detect_distro returns None when /etc/os-release doesn't exist."""
        mock_exists.return_value = False
        assert detect_distro() is None

    @patch("pathlib.Path.read_text")
    @patch("pathlib.Path.exists")
    def test_detects_fedora(self, mock_exists, mock_read):
        """detect_distro detects Fedora."""
        mock_exists.return_value = True
        mock_read.return_value = 'NAME="Fedora Linux"\nID=fedora\nVERSION_ID=39'
        assert detect_distro() == "fedora"

    @patch("pathlib.Path.read_text")
    @patch("pathlib.Path.exists")
    def test_detects_ubuntu(self, mock_exists, mock_read):
        """detect_distro detects Ubuntu."""
        mock_exists.return_value = True
        mock_read.return_value = 'NAME="Ubuntu"\nID=ubuntu\nVERSION_ID="22.04"'
        assert detect_distro() == "ubuntu"


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
    def test_handles_resolution_failure(self, mock_getaddrinfo):
        """resolve_hostname handles resolution failure."""
        import socket
        mock_getaddrinfo.side_effect = socket.gaierror("Name resolution failed")
        ipv4, ipv6 = resolve_hostname("nonexistent.invalid")
        assert ipv4 == []
        assert ipv6 == []


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

    @patch("net.utils.resolve_hostname")
    def test_hostname_resolution(self, mock_resolve):
        """Hostnames are resolved to IPs."""
        mock_resolve.return_value = (["93.184.216.34"], [])
        nf = NetworkFilter(
            hostname_filter=HostnameFilter(
                mode=FilterMode.WHITELIST,
                hosts=["example.com"],
            ),
        )
        v4, v6 = generate_iptables_rules(nf)
        assert any("93.184.216.34" in r for r in v4)


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
        """Port forwards are included with -T flag."""
        nf = NetworkFilter(
            localhost_access=LocalhostAccess(ports=[5432, 6379]),
        )
        args = generate_pasta_args(nf)
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

    @patch("net.pasta.check_pasta")
    def test_installed(self, mock_check):
        """Returns installed status when installed."""
        mock_check.return_value = True
        installed, message = get_pasta_status()
        assert installed is True
        assert "installed" in message

    @patch("net.pasta.check_pasta")
    @patch("net.pasta.get_install_instructions")
    def test_not_installed(self, mock_instructions, mock_check):
        """Returns install instructions when not installed."""
        mock_check.return_value = False
        mock_instructions.return_value = "sudo apt install passt"
        installed, message = get_pasta_status()
        assert installed is False
        assert "apt" in message
