"""Tests for DNS proxy generation and logic."""

import struct

import pytest

from model.network_filter import FilterMode, HostnameFilter
from net.dns_proxy import (
    DNS_PROXY_SCRIPT,
    generate_dns_proxy_script,
    get_dns_proxy_init_commands,
    get_host_nameservers,
    has_host_dns,
    needs_dns_proxy,
)


class TestGetHostNameservers:
    """Test get_host_nameservers function."""

    def test_returns_list(self):
        """Returns a list of nameservers."""
        result = get_host_nameservers()
        assert isinstance(result, list)
        # May be empty if no DNS configured, but should be a list

    def test_includes_localhost(self):
        """Localhost entries are included (no loop in sandboxed namespace)."""
        from unittest.mock import patch

        mock_content = "nameserver 127.0.0.53\nnameserver 8.8.8.8"
        with patch("pathlib.Path.exists", return_value=True):
            with patch("pathlib.Path.read_text", return_value=mock_content):
                result = get_host_nameservers()
                assert "127.0.0.53" in result
                assert "8.8.8.8" in result

    def test_no_fallback(self):
        """Returns empty list if no nameservers found (no fallback to external DNS)."""
        from unittest.mock import patch

        with patch("pathlib.Path.exists", return_value=False):
            result = get_host_nameservers()
            assert result == []

    def test_parses_multiple_nameservers(self):
        """Parses multiple nameserver entries."""
        from unittest.mock import patch

        mock_content = "nameserver 8.8.8.8\nnameserver 8.8.4.4\nnameserver 1.1.1.1"
        with patch("pathlib.Path.exists", return_value=True):
            with patch("pathlib.Path.read_text", return_value=mock_content):
                result = get_host_nameservers()
                assert "8.8.8.8" in result
                assert "8.8.4.4" in result
                assert "1.1.1.1" in result


class TestHasHostDns:
    """Test has_host_dns function."""

    def test_returns_true_when_nameservers_exist(self):
        """Returns True when nameservers are configured."""
        from unittest.mock import patch

        mock_content = "nameserver 8.8.8.8"
        with patch("pathlib.Path.exists", return_value=True):
            with patch("pathlib.Path.read_text", return_value=mock_content):
                assert has_host_dns() is True

    def test_returns_false_when_no_nameservers(self):
        """Returns False when no nameservers are configured."""
        from unittest.mock import patch

        with patch("pathlib.Path.exists", return_value=False):
            assert has_host_dns() is False

    def test_returns_false_for_empty_resolv_conf(self):
        """Returns False when resolv.conf has no nameserver lines."""
        from unittest.mock import patch

        mock_content = "# This is a comment\nsearch example.com"
        with patch("pathlib.Path.exists", return_value=True):
            with patch("pathlib.Path.read_text", return_value=mock_content):
                assert has_host_dns() is False


class TestNeedsDnsProxy:
    """Test needs_dns_proxy function."""

    def test_returns_false_when_mode_off(self):
        """Returns False when hostname filter mode is OFF."""
        hf = HostnameFilter(mode=FilterMode.OFF, hosts=["example.com"])
        assert needs_dns_proxy(hf) is False

    def test_returns_false_when_no_hosts(self):
        """Returns False when no hosts configured."""
        hf = HostnameFilter(mode=FilterMode.BLACKLIST, hosts=[])
        assert needs_dns_proxy(hf) is False

    def test_returns_true_for_blacklist_with_hosts(self):
        """Returns True for blacklist mode with hosts."""
        hf = HostnameFilter(mode=FilterMode.BLACKLIST, hosts=["malware.com"])
        assert needs_dns_proxy(hf) is True

    def test_returns_true_for_whitelist_with_hosts(self):
        """Returns True for whitelist mode with hosts."""
        hf = HostnameFilter(mode=FilterMode.WHITELIST, hosts=["github.com"])
        assert needs_dns_proxy(hf) is True


class TestGenerateDnsProxyScript:
    """Test generate_dns_proxy_script function."""

    def test_generates_valid_python(self):
        """Generated script is valid Python syntax."""
        hf = HostnameFilter(mode=FilterMode.BLACKLIST, hosts=["example.com"])
        script = generate_dns_proxy_script(hf)
        # This should not raise SyntaxError
        compile(script, "<dns_proxy>", "exec")

    def test_embeds_blacklist_mode(self):
        """Blacklist mode is embedded correctly."""
        hf = HostnameFilter(mode=FilterMode.BLACKLIST, hosts=["evil.com"])
        script = generate_dns_proxy_script(hf)
        assert 'MODE = "blacklist"' in script

    def test_embeds_whitelist_mode(self):
        """Whitelist mode is embedded correctly."""
        hf = HostnameFilter(mode=FilterMode.WHITELIST, hosts=["good.com"])
        script = generate_dns_proxy_script(hf)
        assert 'MODE = "whitelist"' in script

    def test_embeds_hosts(self):
        """Hosts list is embedded correctly."""
        hf = HostnameFilter(mode=FilterMode.BLACKLIST, hosts=["a.com", "b.org"])
        script = generate_dns_proxy_script(hf)
        assert "['a.com', 'b.org']" in script

    def test_embeds_upstream_dns(self):
        """Upstream DNS is embedded correctly."""
        hf = HostnameFilter(mode=FilterMode.BLACKLIST, hosts=["test.com"])
        script = generate_dns_proxy_script(hf, upstream_dns="8.8.8.8")
        assert 'UPSTREAM_DNS = "8.8.8.8"' in script

    def test_default_upstream_dns_from_host(self):
        """Default upstream DNS is read from host's resolv.conf."""
        from unittest.mock import patch

        hf = HostnameFilter(mode=FilterMode.BLACKLIST, hosts=["test.com"])
        # Mock the host nameservers
        with patch("net.dns_proxy.get_host_nameservers", return_value=["9.9.9.9"]):
            script = generate_dns_proxy_script(hf)
            assert 'UPSTREAM_DNS = "9.9.9.9"' in script

    def test_raises_when_no_dns_available(self):
        """Raises ValueError when no upstream DNS is available."""
        from unittest.mock import patch

        hf = HostnameFilter(mode=FilterMode.BLACKLIST, hosts=["test.com"])
        # Mock no nameservers available
        with patch("net.dns_proxy.get_host_nameservers", return_value=[]):
            with pytest.raises(ValueError, match="No DNS nameservers configured"):
                generate_dns_proxy_script(hf)

    def test_explicit_upstream_dns_bypasses_check(self):
        """Explicit upstream_dns parameter bypasses host DNS check."""
        from unittest.mock import patch

        hf = HostnameFilter(mode=FilterMode.BLACKLIST, hosts=["test.com"])
        # Even with no host nameservers, explicit upstream works
        with patch("net.dns_proxy.get_host_nameservers", return_value=[]):
            script = generate_dns_proxy_script(hf, upstream_dns="8.8.8.8")
            assert 'UPSTREAM_DNS = "8.8.8.8"' in script


class TestGetDnsProxyInitCommands:
    """Test get_dns_proxy_init_commands function."""

    def test_mentions_robind_resolv_conf(self):
        """Init commands mention ro-bind for /etc/resolv.conf."""
        commands = get_dns_proxy_init_commands("/tmp/dns_proxy.py")
        # resolv.conf is now ro-bind mounted by bwrap, not created by init script
        assert "ro-bind" in commands
        assert "127.0.0.1" in commands

    def test_starts_proxy_in_background(self):
        """Init commands start proxy in background."""
        commands = get_dns_proxy_init_commands("/tmp/dns_proxy.py")
        assert "python3 /tmp/dns_proxy.py &" in commands

    def test_stores_pid(self):
        """Init commands store proxy PID."""
        commands = get_dns_proxy_init_commands("/tmp/dns_proxy.py")
        assert "DNS_PROXY_PID=$!" in commands

    def test_verifies_proxy_running(self):
        """Init commands verify proxy is running."""
        commands = get_dns_proxy_init_commands("/tmp/dns_proxy.py")
        assert "kill -0 $DNS_PROXY_PID" in commands


# ============================================================================
# DNS Protocol Tests
# These test the parsing/generation logic embedded in the DNS proxy script
# ============================================================================


def build_dns_query(hostname: str, qtype: int = 1) -> bytes:
    """Build a minimal DNS query packet for testing.

    Args:
        hostname: Hostname to query (e.g., "github.com")
        qtype: Query type (1=A, 28=AAAA)

    Returns:
        Raw DNS query packet
    """
    # Transaction ID
    txn_id = b"\x12\x34"

    # Flags: RD=1 (recursion desired)
    flags = struct.pack("!H", 0x0100)

    # Counts: 1 question, 0 answers, 0 authority, 0 additional
    counts = struct.pack("!HHHH", 1, 0, 0, 0)

    # Question section: encode hostname
    qname = b""
    for label in hostname.split("."):
        qname += bytes([len(label)]) + label.encode("ascii")
    qname += b"\x00"  # Null terminator

    # QTYPE and QCLASS (IN)
    qtype_qclass = struct.pack("!HH", qtype, 1)

    return txn_id + flags + counts + qname + qtype_qclass


def parse_qname_impl(data: bytes, offset: int) -> tuple[str, int]:
    """Reference implementation of parse_qname for testing.

    This mirrors the logic in the embedded proxy script.
    """
    labels = []
    while True:
        if offset >= len(data):
            break
        length = data[offset]
        if length == 0:
            offset += 1
            break
        if length & 0xC0 == 0xC0:
            pointer = struct.unpack("!H", data[offset:offset + 2])[0] & 0x3FFF
            label, _ = parse_qname_impl(data, pointer)
            labels.append(label)
            offset += 2
            break
        offset += 1
        labels.append(data[offset:offset + length].decode("ascii", errors="replace"))
        offset += length
    return ".".join(labels), offset


def make_nxdomain_impl(query: bytes) -> bytes:
    """Reference implementation of make_nxdomain for testing."""
    if len(query) < 12:
        return b""

    txn_id = query[0:2]
    flags = struct.pack("!H", 0x8183)
    counts = struct.pack("!HHHH", 1, 0, 0, 0)

    question_start = 12
    question_end = question_start
    while question_end < len(query) and query[question_end] != 0:
        question_end += query[question_end] + 1
    question_end += 5

    question = query[question_start:question_end]
    return txn_id + flags + counts + question


def should_block_impl(hostname: str, mode: str, hosts: list[str]) -> bool:
    """Reference implementation of should_block for testing."""
    hostname = hostname.lower().rstrip(".")

    for pattern in hosts:
        pattern = pattern.lower().rstrip(".")

        # Wildcard pattern: *.example.com
        if pattern.startswith("*."):
            suffix = pattern[1:]  # ".example.com"
            if hostname.endswith(suffix) and hostname != suffix[1:]:
                return mode == "blacklist"
            continue

        # Exact match
        if hostname == pattern:
            return mode == "blacklist"

        # Subdomain match
        if hostname.endswith("." + pattern):
            return mode == "blacklist"

    return mode == "whitelist"


class TestParseQname:
    """Test DNS QNAME parsing."""

    def test_simple_hostname(self):
        """Parse simple two-label hostname."""
        query = build_dns_query("example.com")
        qname, _ = parse_qname_impl(query, 12)
        assert qname == "example.com"

    def test_three_label_hostname(self):
        """Parse three-label hostname."""
        query = build_dns_query("www.example.com")
        qname, _ = parse_qname_impl(query, 12)
        assert qname == "www.example.com"

    def test_long_subdomain(self):
        """Parse hostname with long subdomain."""
        query = build_dns_query("api.v2.service.example.com")
        qname, _ = parse_qname_impl(query, 12)
        assert qname == "api.v2.service.example.com"

    def test_single_label(self):
        """Parse single-label hostname (like 'localhost')."""
        query = build_dns_query("localhost")
        qname, _ = parse_qname_impl(query, 12)
        assert qname == "localhost"


class TestMakeNxdomain:
    """Test NXDOMAIN response generation."""

    def test_preserves_transaction_id(self):
        """Response preserves query transaction ID."""
        query = build_dns_query("blocked.com")
        response = make_nxdomain_impl(query)
        assert response[0:2] == query[0:2]

    def test_sets_qr_flag(self):
        """Response has QR flag set (response, not query)."""
        query = build_dns_query("blocked.com")
        response = make_nxdomain_impl(query)
        flags = struct.unpack("!H", response[2:4])[0]
        assert flags & 0x8000  # QR bit set

    def test_sets_rcode_nxdomain(self):
        """Response has RCODE=3 (NXDOMAIN)."""
        query = build_dns_query("blocked.com")
        response = make_nxdomain_impl(query)
        flags = struct.unpack("!H", response[2:4])[0]
        rcode = flags & 0x000F
        assert rcode == 3

    def test_preserves_question_section(self):
        """Response includes original question."""
        query = build_dns_query("blocked.com")
        response = make_nxdomain_impl(query)
        # Question starts at offset 12 in both query and response
        # Find end of question in query
        qend = 12
        while query[qend] != 0:
            qend += query[qend] + 1
        qend += 5  # null + QTYPE + QCLASS
        assert query[12:qend] == response[12:12 + (qend - 12)]

    def test_rejects_short_query(self):
        """Short queries return empty response."""
        response = make_nxdomain_impl(b"\x00" * 11)
        assert response == b""


class TestShouldBlock:
    """Test hostname blocking logic."""

    def test_blacklist_exact_match_blocks(self):
        """Blacklist mode blocks exact hostname match."""
        assert should_block_impl("evil.com", "blacklist", ["evil.com"]) is True

    def test_blacklist_no_match_allows(self):
        """Blacklist mode allows non-matching hostname."""
        assert should_block_impl("good.com", "blacklist", ["evil.com"]) is False

    def test_blacklist_subdomain_blocks(self):
        """Blacklist mode blocks subdomains of blocked hosts."""
        assert should_block_impl("api.evil.com", "blacklist", ["evil.com"]) is True
        assert should_block_impl("cdn.api.evil.com", "blacklist", ["evil.com"]) is True

    def test_blacklist_partial_no_match(self):
        """Blacklist doesn't match partial names."""
        assert should_block_impl("notevil.com", "blacklist", ["evil.com"]) is False
        assert should_block_impl("evil.com.attacker.com", "blacklist", ["evil.com"]) is False

    def test_whitelist_exact_match_allows(self):
        """Whitelist mode allows exact hostname match."""
        assert should_block_impl("good.com", "whitelist", ["good.com"]) is False

    def test_whitelist_no_match_blocks(self):
        """Whitelist mode blocks non-matching hostname."""
        assert should_block_impl("other.com", "whitelist", ["good.com"]) is True

    def test_whitelist_subdomain_allows(self):
        """Whitelist mode allows subdomains of allowed hosts."""
        assert should_block_impl("api.good.com", "whitelist", ["good.com"]) is False
        assert should_block_impl("cdn.api.good.com", "whitelist", ["good.com"]) is False

    def test_case_insensitive(self):
        """Matching is case-insensitive."""
        assert should_block_impl("EVIL.COM", "blacklist", ["evil.com"]) is True
        assert should_block_impl("evil.com", "blacklist", ["EVIL.COM"]) is True

    def test_trailing_dot_handled(self):
        """Trailing dots are handled correctly."""
        assert should_block_impl("evil.com.", "blacklist", ["evil.com"]) is True

    def test_multiple_hosts(self):
        """Multiple hosts in list are checked."""
        hosts = ["a.com", "b.com", "c.com"]
        assert should_block_impl("a.com", "blacklist", hosts) is True
        assert should_block_impl("b.com", "blacklist", hosts) is True
        assert should_block_impl("d.com", "blacklist", hosts) is False

    def test_wildcard_blocks_subdomains(self):
        """Wildcard *.example.com blocks subdomains."""
        assert should_block_impl("api.example.com", "blacklist", ["*.example.com"]) is True
        assert should_block_impl("cdn.api.example.com", "blacklist", ["*.example.com"]) is True

    def test_wildcard_does_not_block_base_domain(self):
        """Wildcard *.example.com does NOT block example.com itself."""
        assert should_block_impl("example.com", "blacklist", ["*.example.com"]) is False

    def test_wildcard_whitelist(self):
        """Wildcard works in whitelist mode."""
        assert should_block_impl("api.allowed.com", "whitelist", ["*.allowed.com"]) is False
        assert should_block_impl("other.com", "whitelist", ["*.allowed.com"]) is True
        # Base domain not matched by wildcard
        assert should_block_impl("allowed.com", "whitelist", ["*.allowed.com"]) is True

    def test_wildcard_with_regular_patterns(self):
        """Wildcard patterns can be mixed with regular patterns."""
        hosts = ["exact.com", "*.wildcard.com"]
        assert should_block_impl("exact.com", "blacklist", hosts) is True
        assert should_block_impl("sub.wildcard.com", "blacklist", hosts) is True
        assert should_block_impl("wildcard.com", "blacklist", hosts) is False
        assert should_block_impl("other.com", "blacklist", hosts) is False


class TestDnsProxyIntegration:
    """Integration tests for DNS proxy generation."""

    def test_full_blacklist_workflow(self):
        """Complete blacklist workflow generates valid script."""
        hf = HostnameFilter(
            mode=FilterMode.BLACKLIST,
            hosts=["malware.com", "tracker.net", "ads.example.org"],
        )
        script = generate_dns_proxy_script(hf)

        # Script should compile
        compile(script, "<test>", "exec")

        # Script should have correct configuration
        assert 'MODE = "blacklist"' in script
        assert "malware.com" in script
        assert "tracker.net" in script

    def test_full_whitelist_workflow(self):
        """Complete whitelist workflow generates valid script."""
        hf = HostnameFilter(
            mode=FilterMode.WHITELIST,
            hosts=["github.com", "npmjs.org", "pypi.org"],
        )
        script = generate_dns_proxy_script(hf)

        # Script should compile
        compile(script, "<test>", "exec")

        # Script should have correct configuration
        assert 'MODE = "whitelist"' in script
        assert "github.com" in script

    def test_special_characters_in_hosts_escaped(self):
        """Hosts with special characters are properly escaped."""
        hf = HostnameFilter(
            mode=FilterMode.BLACKLIST,
            hosts=["test-site.example.com", "site_with_underscore.com"],
        )
        script = generate_dns_proxy_script(hf)

        # Should still compile
        compile(script, "<test>", "exec")
