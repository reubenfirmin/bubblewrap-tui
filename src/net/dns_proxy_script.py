#!/usr/bin/env python3
"""Minimal DNS proxy for hostname filtering inside bubblewrap sandbox.

This proxy intercepts DNS queries on 127.0.0.1:53 and either:
- Returns NXDOMAIN for blocked hostnames
- Forwards allowed queries to the upstream DNS server

No external dependencies - uses only Python stdlib.

NOTE: This file is inlined into dns_proxy.py by build.py.
The placeholders (upstream_dns, upstream_port, mode, hosts) are replaced at runtime.
"""

import socket
import struct
import sys
import os

# Configuration injected at generation time
UPSTREAM_DNS = "{upstream_dns}"
UPSTREAM_PORT = {upstream_port}
MODE = "{mode}"  # "whitelist" or "blacklist"
HOSTS = {hosts}


MAX_COMPRESSION_DEPTH = 10  # Limit recursion to prevent DoS from pointer loops


def parse_qname(data: bytes, offset: int, depth: int = 0) -> tuple[str, int]:
    """Extract hostname from DNS query packet.

    DNS names are encoded as length-prefixed labels:
    \\x06github\\x03com\\x00 -> github.com

    Args:
        data: Raw DNS packet bytes
        offset: Starting offset in packet (usually 12 for queries)
        depth: Current recursion depth for compression pointer tracking

    Returns:
        Tuple of (hostname, new_offset)
    """
    if depth > MAX_COMPRESSION_DEPTH:
        # Reject packets with excessive compression pointer depth
        return "", offset

    labels = []
    while True:
        if offset >= len(data):
            break
        length = data[offset]
        if length == 0:
            offset += 1
            break
        # Check for compression pointer (0xC0)
        if length & 0xC0 == 0xC0:
            # Compression not expected in queries, but handle gracefully
            if offset + 2 > len(data):
                break  # Malformed packet
            pointer = struct.unpack("!H", data[offset:offset+2])[0] & 0x3FFF
            label, _ = parse_qname(data, pointer, depth + 1)
            labels.append(label)
            offset += 2
            break
        offset += 1
        labels.append(data[offset:offset+length].decode("ascii", errors="replace"))
        offset += length
    return ".".join(labels), offset


def make_nxdomain(query: bytes) -> bytes:
    """Build NXDOMAIN response for a DNS query.

    Sets rcode=3 (NXDOMAIN) and QR=1 (response), RA=1 (recursion available).

    Args:
        query: Original DNS query packet

    Returns:
        DNS response packet with NXDOMAIN status
    """
    if len(query) < 12:
        return b""

    # Copy transaction ID and question
    txn_id = query[0:2]

    # Flags: QR=1 (response), OPCODE=0, AA=0, TC=0, RD=1, RA=1, Z=0, RCODE=3 (NXDOMAIN)
    # Binary: 1000 0001 1000 0011 = 0x8183
    flags = struct.pack("!H", 0x8183)

    # QDCOUNT=1, ANCOUNT=0, NSCOUNT=0, ARCOUNT=0
    counts = struct.pack("!HHHH", 1, 0, 0, 0)

    # Copy question section from query
    question_start = 12
    question_end = question_start
    while question_end < len(query) and query[question_end] != 0:
        question_end += query[question_end] + 1
    question_end += 5  # null byte + QTYPE (2) + QCLASS (2)

    question = query[question_start:question_end]

    return txn_id + flags + counts + question


def forward(query: bytes) -> bytes:
    """Forward DNS query to upstream server.

    Args:
        query: DNS query packet

    Returns:
        DNS response from upstream, or empty bytes on error
    """
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(5.0)
        sock.sendto(query, (UPSTREAM_DNS, UPSTREAM_PORT))
        response, _ = sock.recvfrom(4096)
        sock.close()
        return response
    except Exception:
        return b""


def should_block(hostname: str) -> bool:
    """Check if hostname should be blocked.

    Supports:
    - Exact match: "example.com" matches "example.com"
    - Subdomain match: "example.com" matches "api.example.com"
    - Wildcard match: "*.example.com" matches "api.example.com" but NOT "example.com"

    Args:
        hostname: Hostname to check (lowercase)

    Returns:
        True if hostname should be blocked
    """
    hostname = hostname.lower().rstrip(".")

    for pattern in HOSTS:
        pattern = pattern.lower().rstrip(".")

        # Wildcard pattern: *.example.com
        if pattern.startswith("*."):
            suffix = pattern[1:]  # ".example.com"
            if hostname.endswith(suffix) and hostname != suffix[1:]:
                return MODE == "blacklist"
            continue

        # Exact match
        if hostname == pattern:
            return MODE == "blacklist"

        # Subdomain match (e.g., "github.com" matches "api.github.com")
        if hostname.endswith("." + pattern):
            return MODE == "blacklist"

    # No match found
    return MODE == "whitelist"


def main():
    """Main proxy loop."""
    # Bind to localhost:53
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    try:
        sock.bind(("127.0.0.1", 53))
    except PermissionError:
        print("DNS proxy: Permission denied binding to port 53", file=sys.stderr)
        sys.exit(1)
    except OSError as e:
        print(f"DNS proxy: Failed to bind: {{e}}", file=sys.stderr)
        sys.exit(1)

    # Signal ready by writing to fd 3 if available (for init script coordination)
    try:
        os.write(3, b"ready\n")
        os.close(3)
    except OSError:
        pass  # fd 3 not available, continue anyway

    while True:
        try:
            data, addr = sock.recvfrom(4096)
            if len(data) < 12:
                continue

            # Parse question name
            qname, _ = parse_qname(data, 12)

            if should_block(qname):
                response = make_nxdomain(data)
            else:
                response = forward(data)

            if response:
                sock.sendto(response, addr)
        except Exception:
            continue


if __name__ == "__main__":
    main()
