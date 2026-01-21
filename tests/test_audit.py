"""Tests for net/audit.py - Network traffic auditing via pcap parsing."""

from __future__ import annotations

import socket
import struct
import tempfile
from collections import Counter
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from net.audit import (
    AuditResult,
    _format_bytes,
    _is_private_ip,
    _is_private_ipv6,
    _parse_basic,
    parse_pcap,
)


class TestAuditResult:
    """Tests for AuditResult dataclass."""

    def test_empty_result(self):
        """Default values are empty counters/dicts."""
        result = AuditResult()
        assert result.dest_ips == Counter()
        assert result.bytes_sent == Counter()
        assert result.bytes_recv == Counter()
        assert result.dns_queries == {}
        assert result.ip_to_hostname == {}

    def test_total_connections(self):
        """total_connections sums dest_ips counter values."""
        result = AuditResult()
        result.dest_ips["1.1.1.1"] = 5
        result.dest_ips["8.8.8.8"] = 3
        assert result.total_connections() == 8

    def test_total_connections_empty(self):
        """total_connections returns 0 for empty result."""
        result = AuditResult()
        assert result.total_connections() == 0

    def test_total_bytes_sent(self):
        """total_bytes_sent sums bytes_sent counter values."""
        result = AuditResult()
        result.bytes_sent["1.1.1.1"] = 1000
        result.bytes_sent["8.8.8.8"] = 500
        assert result.total_bytes_sent() == 1500

    def test_total_bytes_sent_empty(self):
        """total_bytes_sent returns 0 for empty result."""
        result = AuditResult()
        assert result.total_bytes_sent() == 0

    def test_total_bytes_recv(self):
        """total_bytes_recv sums bytes_recv counter values."""
        result = AuditResult()
        result.bytes_recv["1.1.1.1"] = 2000
        result.bytes_recv["8.8.8.8"] = 3000
        assert result.total_bytes_recv() == 5000

    def test_total_bytes_recv_empty(self):
        """total_bytes_recv returns 0 for empty result."""
        result = AuditResult()
        assert result.total_bytes_recv() == 0

    def test_unique_hosts_returns_sorted(self):
        """unique_hosts returns sorted list."""
        result = AuditResult()
        result.dest_ips["8.8.8.8"] = 1
        result.dest_ips["1.1.1.1"] = 1
        result.dest_ips["4.4.4.4"] = 1
        hosts = result.unique_hosts()
        assert hosts == ["1.1.1.1", "4.4.4.4", "8.8.8.8"]

    def test_unique_hosts_prefers_hostname(self):
        """unique_hosts returns hostname when ip_to_hostname mapping exists."""
        result = AuditResult()
        result.dest_ips["8.8.8.8"] = 1
        result.ip_to_hostname["8.8.8.8"] = "dns.google"
        hosts = result.unique_hosts()
        assert "dns.google" in hosts
        assert "8.8.8.8" not in hosts

    def test_unique_hosts_falls_back_to_ip(self):
        """unique_hosts returns IP when no hostname mapping."""
        result = AuditResult()
        result.dest_ips["1.1.1.1"] = 1
        # No ip_to_hostname entry for 1.1.1.1
        hosts = result.unique_hosts()
        assert "1.1.1.1" in hosts

    def test_unique_hosts_mixed(self):
        """unique_hosts correctly handles mix of hostnames and IPs."""
        result = AuditResult()
        result.dest_ips["8.8.8.8"] = 1
        result.dest_ips["1.1.1.1"] = 1
        result.ip_to_hostname["8.8.8.8"] = "dns.google"
        hosts = result.unique_hosts()
        assert "dns.google" in hosts
        assert "1.1.1.1" in hosts
        assert "8.8.8.8" not in hosts


class TestIsPrivateIP:
    """Tests for _is_private_ip function."""

    def test_10_x_x_x_is_private(self):
        """10.0.0.0/8 is private."""
        assert _is_private_ip("10.0.0.1") is True
        assert _is_private_ip("10.255.255.255") is True
        assert _is_private_ip("10.50.100.200") is True

    def test_172_16_to_31_is_private(self):
        """172.16.0.0/12 is private."""
        assert _is_private_ip("172.16.0.1") is True
        assert _is_private_ip("172.31.255.255") is True
        assert _is_private_ip("172.20.10.5") is True
        # 172.15 and 172.32 are NOT private
        assert _is_private_ip("172.15.0.1") is False
        assert _is_private_ip("172.32.0.1") is False

    def test_192_168_x_x_is_private(self):
        """192.168.0.0/16 is private."""
        assert _is_private_ip("192.168.0.1") is True
        assert _is_private_ip("192.168.255.255") is True
        assert _is_private_ip("192.168.1.100") is True

    def test_127_x_x_x_is_private(self):
        """Loopback 127.0.0.0/8 is private."""
        assert _is_private_ip("127.0.0.1") is True
        assert _is_private_ip("127.255.255.255") is True

    def test_169_254_x_x_is_private(self):
        """Link-local 169.254.0.0/16 is private."""
        assert _is_private_ip("169.254.0.1") is True
        assert _is_private_ip("169.254.255.255") is True

    def test_8_8_8_8_is_public(self):
        """Google DNS 8.8.8.8 is public."""
        assert _is_private_ip("8.8.8.8") is False

    def test_1_1_1_1_is_public(self):
        """Cloudflare DNS 1.1.1.1 is public."""
        assert _is_private_ip("1.1.1.1") is False

    def test_other_public_ips(self):
        """Other public IPs are correctly identified."""
        assert _is_private_ip("93.184.216.34") is False  # example.com
        assert _is_private_ip("140.82.121.3") is False  # github.com
        assert _is_private_ip("208.67.222.222") is False  # OpenDNS


class TestIsPrivateIPv6:
    """Tests for _is_private_ipv6 function."""

    def test_fe80_link_local_is_private(self):
        """fe80::/10 link-local is private."""
        assert _is_private_ipv6("fe80::1") is True
        assert _is_private_ipv6("fe80::abcd:ef01:2345:6789") is True
        assert _is_private_ipv6("FE80::1") is True  # Case insensitive

    def test_fc_unique_local_is_private(self):
        """fc00::/7 unique local addresses are private."""
        assert _is_private_ipv6("fc00::1") is True
        assert _is_private_ipv6("fcab:cdef:1234:5678::1") is True

    def test_fd_unique_local_is_private(self):
        """fd00::/8 unique local addresses are private."""
        assert _is_private_ipv6("fd00::1") is True
        assert _is_private_ipv6("fdab:cdef:1234:5678::1") is True

    def test_loopback_is_private(self):
        """::1 loopback is private."""
        assert _is_private_ipv6("::1") is True

    def test_multicast_is_private(self):
        """ff00::/8 multicast is private."""
        assert _is_private_ipv6("ff00::1") is True
        assert _is_private_ipv6("ff02::1") is True
        assert _is_private_ipv6("FF02::1") is True  # Case insensitive

    def test_global_unicast_is_public(self):
        """Global unicast addresses are public."""
        assert _is_private_ipv6("2001:db8::1") is False
        assert _is_private_ipv6("2606:2800:220:1:248:1893:25c8:1946") is False
        assert _is_private_ipv6("2607:f8b0:4004:800::200e") is False  # google.com


class TestFormatBytes:
    """Tests for _format_bytes function."""

    def test_bytes(self):
        """Under 1KB shows 'X B'."""
        assert _format_bytes(0) == "0 B"
        assert _format_bytes(1) == "1 B"
        assert _format_bytes(512) == "512 B"
        assert _format_bytes(1023) == "1023 B"

    def test_kilobytes(self):
        """1KB-1MB shows 'X.X KB'."""
        assert _format_bytes(1024) == "1.0 KB"
        assert _format_bytes(1536) == "1.5 KB"
        assert _format_bytes(10240) == "10.0 KB"
        assert _format_bytes(1024 * 1024 - 1) == "1024.0 KB"

    def test_megabytes(self):
        """1MB-1GB shows 'X.X MB'."""
        assert _format_bytes(1024 * 1024) == "1.0 MB"
        assert _format_bytes(1024 * 1024 * 10) == "10.0 MB"
        assert _format_bytes(1024 * 1024 * 500) == "500.0 MB"

    def test_gigabytes(self):
        """Over 1GB shows 'X.X GB'."""
        assert _format_bytes(1024 * 1024 * 1024) == "1.0 GB"
        assert _format_bytes(1024 * 1024 * 1024 * 2) == "2.0 GB"


class TestParsePcap:
    """Tests for parse_pcap function."""

    def test_empty_file(self, tmp_path):
        """Returns empty AuditResult for empty file."""
        pcap_file = tmp_path / "empty.pcap"
        pcap_file.write_bytes(b"")
        result = parse_pcap(pcap_file)
        assert result.total_connections() == 0

    def test_nonexistent_file(self, tmp_path):
        """Raises error for nonexistent file."""
        pcap_file = tmp_path / "nonexistent.pcap"
        with pytest.raises(FileNotFoundError):
            parse_pcap(pcap_file)

    def test_fallback_without_dpkt(self, tmp_path):
        """Falls back to basic parsing when dpkt unavailable."""
        # Create minimal valid pcap with one IPv4 packet to public IP
        pcap_file = tmp_path / "test.pcap"
        pcap_data = _create_minimal_pcap_with_ipv4_packet("8.8.8.8")
        pcap_file.write_bytes(pcap_data)

        # Mock dpkt import to fail
        with patch.dict("sys.modules", {"dpkt": None}):
            with patch("net.audit._parse_with_dpkt", side_effect=ImportError):
                result = parse_pcap(pcap_file)
                # Should have parsed the packet via _parse_basic
                assert "8.8.8.8" in result.dest_ips


class TestParseBasic:
    """Tests for _parse_basic function (basic pcap parsing without dpkt)."""

    def test_invalid_magic(self, tmp_path):
        """Returns empty result for non-pcap file."""
        pcap_file = tmp_path / "invalid.pcap"
        pcap_file.write_bytes(b"not a pcap file at all")
        result = _parse_basic(pcap_file)
        assert result.total_connections() == 0

    def test_little_endian_pcap(self, tmp_path):
        """Parses little-endian pcap correctly."""
        pcap_file = tmp_path / "le.pcap"
        pcap_data = _create_minimal_pcap_with_ipv4_packet("1.1.1.1", big_endian=False)
        pcap_file.write_bytes(pcap_data)
        result = _parse_basic(pcap_file)
        assert "1.1.1.1" in result.dest_ips

    def test_big_endian_pcap(self, tmp_path):
        """Parses big-endian pcap correctly."""
        pcap_file = tmp_path / "be.pcap"
        pcap_data = _create_minimal_pcap_with_ipv4_packet("1.1.1.1", big_endian=True)
        pcap_file.write_bytes(pcap_data)
        result = _parse_basic(pcap_file)
        assert "1.1.1.1" in result.dest_ips

    def test_ipv4_packet_extraction(self, tmp_path):
        """Extracts IPv4 destination IPs correctly."""
        pcap_file = tmp_path / "ipv4.pcap"
        pcap_data = _create_minimal_pcap_with_ipv4_packet("93.184.216.34")
        pcap_file.write_bytes(pcap_data)
        result = _parse_basic(pcap_file)
        assert "93.184.216.34" in result.dest_ips

    def test_filters_private_ips(self, tmp_path):
        """Doesn't count private IPs in dest_ips."""
        pcap_file = tmp_path / "private.pcap"
        pcap_data = _create_minimal_pcap_with_ipv4_packet("192.168.1.1")
        pcap_file.write_bytes(pcap_data)
        result = _parse_basic(pcap_file)
        assert "192.168.1.1" not in result.dest_ips
        assert result.total_connections() == 0

    def test_truncated_packet_header(self, tmp_path):
        """Handles truncated packet header gracefully."""
        pcap_file = tmp_path / "truncated.pcap"
        # Global header only, no packets
        global_header = _create_pcap_global_header(big_endian=False)
        pcap_file.write_bytes(global_header)
        result = _parse_basic(pcap_file)
        assert result.total_connections() == 0

    def test_truncated_packet_data(self, tmp_path):
        """Handles truncated packet data gracefully."""
        pcap_file = tmp_path / "truncated_data.pcap"
        global_header = _create_pcap_global_header(big_endian=False)
        # Packet header claiming 100 bytes but only providing 10
        packet_header = struct.pack("<IIII", 0, 0, 100, 100)
        packet_data = b"\x00" * 10
        pcap_file.write_bytes(global_header + packet_header + packet_data)
        result = _parse_basic(pcap_file)
        assert result.total_connections() == 0

    def test_multiple_packets(self, tmp_path):
        """Correctly counts multiple packets to same destination."""
        pcap_file = tmp_path / "multi.pcap"
        pcap_data = _create_pcap_with_multiple_packets(
            [("8.8.8.8", 3), ("1.1.1.1", 2)]
        )
        pcap_file.write_bytes(pcap_data)
        result = _parse_basic(pcap_file)
        assert result.dest_ips["8.8.8.8"] == 3
        assert result.dest_ips["1.1.1.1"] == 2


class TestParseDnsResponse:
    """Tests for DNS parsing (requires dpkt)."""

    @pytest.fixture
    def mock_dpkt(self):
        """Mock dpkt module."""
        dpkt_mock = MagicMock()

        # Mock DNS constants
        dpkt_mock.dns.DNS_R = 1
        dpkt_mock.dns.DNS_A = 1
        dpkt_mock.dns.DNS_AAAA = 28

        return dpkt_mock

    def test_dns_response_extracts_hostname_mapping(self, mock_dpkt):
        """DNS response correctly maps hostname to IP."""
        result = AuditResult()

        # Create mock DNS response
        mock_dns = MagicMock()
        mock_dns.qr = mock_dpkt.dns.DNS_R

        mock_question = MagicMock()
        mock_question.name = "example.com"
        mock_dns.qd = [mock_question]

        mock_answer = MagicMock()
        mock_answer.type = mock_dpkt.dns.DNS_A
        mock_answer.rdata = socket.inet_aton("93.184.216.34")
        mock_dns.an = [mock_answer]

        mock_dpkt.dns.DNS.return_value = mock_dns

        with patch.dict("sys.modules", {"dpkt": mock_dpkt}):
            from net.audit import _parse_dns_response

            _parse_dns_response(b"mock_data", result)

        assert result.ip_to_hostname.get("93.184.216.34") == "example.com"
        assert "example.com" in result.dns_queries


# Helper functions for creating test pcap data


def _create_pcap_global_header(big_endian: bool = False) -> bytes:
    """Create a pcap global header.

    The pcap magic number is always 0xa1b2c3d4, but written in the file's
    native endianness. When read as little-endian, LE files give 0xa1b2c3d4
    and BE files give 0xd4c3b2a1.
    """
    endian = ">" if big_endian else "<"
    magic = 0xa1b2c3d4  # Standard pcap magic, written in file's endianness
    return struct.pack(
        endian + "IHHiIII",
        magic,  # Magic number
        2,  # Major version
        4,  # Minor version
        0,  # Timezone offset
        0,  # Timestamp accuracy
        65535,  # Snapshot length
        1,  # Link-layer type (Ethernet)
    )


def _create_ethernet_ipv4_packet(dst_ip: str, src_ip: str = "192.168.1.100") -> bytes:
    """Create a minimal Ethernet + IPv4 packet."""
    # Ethernet header (14 bytes)
    eth_header = (
        b"\x00\x00\x00\x00\x00\x01"  # Destination MAC
        + b"\x00\x00\x00\x00\x00\x02"  # Source MAC
        + b"\x08\x00"  # EtherType (IPv4)
    )

    # IPv4 header (20 bytes minimum)
    src_bytes = socket.inet_aton(src_ip)
    dst_bytes = socket.inet_aton(dst_ip)
    ip_header = (
        b"\x45"  # Version (4) + IHL (5)
        + b"\x00"  # DSCP + ECN
        + b"\x00\x28"  # Total length (40 bytes)
        + b"\x00\x00"  # Identification
        + b"\x40\x00"  # Flags + Fragment offset (Don't Fragment)
        + b"\x40"  # TTL (64)
        + b"\x06"  # Protocol (TCP)
        + b"\x00\x00"  # Header checksum (ignored)
        + src_bytes  # Source IP
        + dst_bytes  # Destination IP
    )

    return eth_header + ip_header


def _create_minimal_pcap_with_ipv4_packet(
    dst_ip: str, big_endian: bool = False
) -> bytes:
    """Create a minimal pcap file with one IPv4 packet."""
    global_header = _create_pcap_global_header(big_endian)
    packet = _create_ethernet_ipv4_packet(dst_ip)

    endian = ">" if big_endian else "<"
    packet_header = struct.pack(
        endian + "IIII",
        0,  # Timestamp seconds
        0,  # Timestamp microseconds
        len(packet),  # Captured length
        len(packet),  # Original length
    )

    return global_header + packet_header + packet


def _create_pcap_with_multiple_packets(
    dst_ips_and_counts: list[tuple[str, int]], big_endian: bool = False
) -> bytes:
    """Create a pcap file with multiple packets to various destinations."""
    data = _create_pcap_global_header(big_endian)
    endian = ">" if big_endian else "<"

    for dst_ip, count in dst_ips_and_counts:
        for _ in range(count):
            packet = _create_ethernet_ipv4_packet(dst_ip)
            packet_header = struct.pack(
                endian + "IIII",
                0,  # Timestamp seconds
                0,  # Timestamp microseconds
                len(packet),  # Captured length
                len(packet),  # Original length
            )
            data += packet_header + packet

    return data
