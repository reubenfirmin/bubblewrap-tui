"""Network traffic auditing via pcap capture.

This module provides traffic analysis for audit mode, parsing pcap files
captured by pasta to extract unique hosts and IPs contacted by the sandbox.
"""

from __future__ import annotations

import socket
import struct
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class AuditResult:
    """Results from analyzing a pcap capture."""

    # Unique destination IPs with connection counts
    dest_ips: Counter[str] = field(default_factory=Counter)

    # Bytes sent to each destination IP
    bytes_sent: Counter[str] = field(default_factory=Counter)

    # Bytes received from each source IP
    bytes_recv: Counter[str] = field(default_factory=Counter)

    # DNS queries seen (hostname -> resolved IPs)
    dns_queries: dict[str, list[str]] = field(default_factory=dict)

    # Reverse DNS cache (IP -> hostname if we saw the query)
    ip_to_hostname: dict[str, str] = field(default_factory=dict)

    def total_connections(self) -> int:
        """Total number of outbound connections."""
        return sum(self.dest_ips.values())

    def total_bytes_sent(self) -> int:
        """Total bytes sent."""
        return sum(self.bytes_sent.values())

    def total_bytes_recv(self) -> int:
        """Total bytes received."""
        return sum(self.bytes_recv.values())

    def unique_hosts(self) -> list[str]:
        """Get list of unique hosts (hostnames where known, IPs otherwise)."""
        hosts = []
        seen_ips = set()

        # Add hostnames for IPs we know
        for ip, hostname in self.ip_to_hostname.items():
            if ip in self.dest_ips:
                hosts.append(hostname)
                seen_ips.add(ip)

        # Add remaining IPs without known hostnames
        for ip in self.dest_ips:
            if ip not in seen_ips:
                hosts.append(ip)

        return sorted(hosts)


def parse_pcap(pcap_path: Path) -> AuditResult:
    """Parse a pcap file and extract network audit information.

    Uses dpkt for lightweight pcap parsing. Falls back to basic parsing
    if dpkt is not available.

    Args:
        pcap_path: Path to the pcap file

    Returns:
        AuditResult with extracted information
    """
    try:
        return _parse_with_dpkt(pcap_path)
    except ImportError:
        # dpkt not installed, try basic parsing
        return _parse_basic(pcap_path)


def _parse_with_dpkt(pcap_path: Path) -> AuditResult:
    """Parse pcap using dpkt library."""
    import dpkt

    result = AuditResult()

    with open(pcap_path, "rb") as f:
        try:
            pcap = dpkt.pcap.Reader(f)
        except (ValueError, dpkt.dpkt.NeedData):
            # Empty or invalid pcap
            return result

        for timestamp, buf in pcap:
            try:
                eth = dpkt.ethernet.Ethernet(buf)
            except (dpkt.dpkt.NeedData, dpkt.dpkt.UnpackError):
                continue

            # Handle IP packets
            if isinstance(eth.data, dpkt.ip.IP):
                ip = eth.data
                src_ip = socket.inet_ntoa(ip.src)
                dst_ip = socket.inet_ntoa(ip.dst)
                pkt_len = len(ip)

                # Outbound: to external destination
                if not _is_private_ip(dst_ip):
                    result.dest_ips[dst_ip] += 1
                    result.bytes_sent[dst_ip] += pkt_len

                # Inbound: from external source
                if not _is_private_ip(src_ip):
                    result.bytes_recv[src_ip] += pkt_len

                # Check for DNS responses
                if isinstance(ip.data, dpkt.udp.UDP):
                    udp = ip.data
                    if udp.sport == 53:  # DNS response
                        _parse_dns_response(udp.data, result)

            # Handle IPv6 packets
            elif isinstance(eth.data, dpkt.ip6.IP6):
                ip6 = eth.data
                src_ip = socket.inet_ntop(socket.AF_INET6, ip6.src)
                dst_ip = socket.inet_ntop(socket.AF_INET6, ip6.dst)
                pkt_len = len(ip6)

                # Outbound: to external destination
                if not _is_private_ipv6(dst_ip):
                    result.dest_ips[dst_ip] += 1
                    result.bytes_sent[dst_ip] += pkt_len

                # Inbound: from external source
                if not _is_private_ipv6(src_ip):
                    result.bytes_recv[src_ip] += pkt_len

    return result


def _parse_dns_response(data: bytes, result: AuditResult) -> None:
    """Parse DNS response to extract hostname -> IP mappings."""
    try:
        import dpkt
        dns = dpkt.dns.DNS(data)

        if dns.qr == dpkt.dns.DNS_R:  # Response
            for q in dns.qd:
                hostname = q.name
                ips = []

                for rr in dns.an:
                    if rr.type == dpkt.dns.DNS_A:
                        ip = socket.inet_ntoa(rr.rdata)
                        ips.append(ip)
                        result.ip_to_hostname[ip] = hostname
                    elif rr.type == dpkt.dns.DNS_AAAA:
                        ip = socket.inet_ntop(socket.AF_INET6, rr.rdata)
                        ips.append(ip)
                        result.ip_to_hostname[ip] = hostname

                if ips:
                    result.dns_queries[hostname] = ips

    except Exception:
        pass  # DNS parsing is best-effort


def _parse_basic(pcap_path: Path) -> AuditResult:
    """Basic pcap parsing without dpkt (limited functionality)."""
    result = AuditResult()

    with open(pcap_path, "rb") as f:
        # Read pcap global header
        global_header = f.read(24)
        if len(global_header) < 24:
            return result

        magic = struct.unpack("<I", global_header[:4])[0]
        if magic == 0xa1b2c3d4:
            endian = "<"
        elif magic == 0xd4c3b2a1:
            endian = ">"
        else:
            return result  # Not a valid pcap

        # Read packets
        max_packet_size = 65535  # Maximum ethernet frame size
        while True:
            packet_header = f.read(16)
            if len(packet_header) < 16:
                break

            _, _, incl_len, _ = struct.unpack(endian + "IIII", packet_header)
            if incl_len > max_packet_size:
                break  # Reject oversized packets to prevent memory exhaustion
            packet_data = f.read(incl_len)
            if len(packet_data) < incl_len:
                break

            # Basic Ethernet + IP parsing
            if len(packet_data) >= 34:  # Ethernet header (14) + IP header (20)
                ethertype = struct.unpack(">H", packet_data[12:14])[0]

                if ethertype == 0x0800:  # IPv4
                    ip_header = packet_data[14:34]
                    dst_ip = socket.inet_ntoa(ip_header[16:20])

                    if not _is_private_ip(dst_ip):
                        result.dest_ips[dst_ip] += 1

    return result


def _is_private_ip(ip: str) -> bool:
    """Check if an IPv4 address is private/local."""
    try:
        parts = [int(p) for p in ip.split(".")]
        if len(parts) != 4:
            return False  # Malformed IP
    except ValueError:
        return False  # Malformed IP (non-numeric parts)
    if parts[0] == 10:
        return True
    if parts[0] == 172 and 16 <= parts[1] <= 31:
        return True
    if parts[0] == 192 and parts[1] == 168:
        return True
    if parts[0] == 127:
        return True
    if parts[0] == 169 and parts[1] == 254:
        return True
    return False


def _is_private_ipv6(ip: str) -> bool:
    """Check if an IPv6 address is private/local."""
    ip_lower = ip.lower()
    if ip_lower.startswith("fe80:"):  # Link-local
        return True
    if ip_lower.startswith("fc") or ip_lower.startswith("fd"):  # Unique local
        return True
    if ip_lower == "::1":  # Loopback
        return True
    if ip_lower.startswith("ff"):  # Multicast
        return True
    return False


def _format_bytes(num_bytes: int) -> str:
    """Format bytes as human-readable string."""
    if num_bytes < 1024:
        return f"{num_bytes} B"
    elif num_bytes < 1024 * 1024:
        return f"{num_bytes / 1024:.1f} KB"
    elif num_bytes < 1024 * 1024 * 1024:
        return f"{num_bytes / (1024 * 1024):.1f} MB"
    else:
        return f"{num_bytes / (1024 * 1024 * 1024):.1f} GB"


def _reverse_dns_lookup(ip: str) -> str | None:
    """Attempt reverse DNS lookup for an IP address.

    Returns the hostname if found, None otherwise.
    """
    try:
        hostname, _, _ = socket.gethostbyaddr(ip)
        return hostname
    except (socket.herror, socket.gaierror, OSError):
        return None


def _resolve_unknown_ips(result: AuditResult) -> None:
    """Attempt to resolve hostnames for IPs without DNS mappings."""
    for ip in result.dest_ips:
        if ip not in result.ip_to_hostname:
            # Skip multicast addresses
            if ip.startswith("ff"):
                continue
            hostname = _reverse_dns_lookup(ip)
            if hostname:
                result.ip_to_hostname[ip] = hostname


def print_audit_summary(result: AuditResult, pcap_path: Path | None = None) -> None:
    """Print a human-readable summary of audit results."""
    print("\n" + "=" * 60)
    print("NETWORK AUDIT RESULTS")
    print("=" * 60)

    if pcap_path and pcap_path.exists():
        print(f"\nCapture file: {pcap_path}")
        print("  (open in Wireshark for detailed analysis)")

    if not result.dest_ips:
        print("\nNo outbound connections detected.")
        print("=" * 60)
        return

    # Resolve IPs without hostname mappings via reverse DNS
    print("\nResolving hostnames...", end=" ", flush=True)
    _resolve_unknown_ips(result)
    print("done.")

    if not result.dest_ips:
        print("\nNo outbound connections detected.")
        print("=" * 60)
        return

    print(f"\nTotal packets: {result.total_connections()}")
    print(f"Unique destinations: {len(result.dest_ips)}")
    print(f"Data sent: {_format_bytes(result.total_bytes_sent())}")
    print(f"Data received: {_format_bytes(result.total_bytes_recv())}")

    # Build per-IP data
    all_ips = set(result.dest_ips.keys()) | set(result.bytes_recv.keys())
    ip_data = []

    for ip in all_ips:
        packets = result.dest_ips.get(ip, 0)
        sent = result.bytes_sent.get(ip, 0)
        recv = result.bytes_recv.get(ip, 0)
        hostname = result.ip_to_hostname.get(ip)
        ip_data.append((ip, sent, recv, packets, hostname))

    # Sort by total data transferred
    ip_data.sort(key=lambda x: x[1] + x[2], reverse=True)

    print("\nTraffic by destination:")
    print()
    print(f"  {'IP':<40}  {'Sent':>10}  {'Recv':>10}  {'Pkts':>6}  Hostname")
    print("  " + "-" * 90)

    for ip, sent, recv, packets, hostname in ip_data[:20]:
        sent_str = _format_bytes(sent)
        recv_str = _format_bytes(recv)
        host_str = hostname if hostname else ""
        print(f"  {ip:<40}  {sent_str:>10}  {recv_str:>10}  {packets:>6}  {host_str}")

    if len(ip_data) > 20:
        print(f"\n  ... and {len(ip_data) - 20} more")

    print("=" * 60)
