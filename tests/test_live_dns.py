"""Opt-in rootless network checks: BUI_TEST_NETWORK=1 uv run ... pytest this file.

Requires pasta, bubblewrap, iptables, and nested user namespaces.
All firewall changes happen inside pasta's disposable network namespace.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

from net.dns_forward import read_dns_forwarding
from net.filtering import create_wrapper_script, validate_filtering_requirements
from net.pasta_args import generate_pasta_args


pytestmark = pytest.mark.skipif(
    os.environ.get("BUI_TEST_NETWORK") != "1",
    reason="Set BUI_TEST_NETWORK=1 to exercise real rootless DNS networking",
)


# Run inside the actual untrusted network and filesystem configuration. Raw
# packets exercise the mounted resolv.conf and TCP fallback without depending
# on an application's DNS cache or an /etc/hosts entry.
DNS_CHECK = r'''
import errno
import socket
import struct
from pathlib import Path

resolver = next(line.split()[1] for line in Path('/etc/resolv.conf').read_text().splitlines()
                if line.startswith('nameserver '))
family = socket.AF_INET6 if ':' in resolver else socket.AF_INET
query = struct.pack('!6H', 0x1234, 0x0100, 1, 0, 0, 0) + b'\x07example\x03com\x00' + struct.pack('!HH', 1, 1)

def read_exact(sock, count):
    result = b''
    while len(result) < count:
        chunk = sock.recv(count - len(result))
        assert chunk, 'DNS TCP response ended early'
        result += chunk
    return result

for transport in (socket.SOCK_DGRAM, socket.SOCK_STREAM):
    with socket.socket(family, transport) as sock:
        sock.settimeout(8)
        sock.connect((resolver, 53))
        if transport == socket.SOCK_DGRAM:
            sock.send(query)
            response = sock.recv(65535)
        else:
            sock.sendall(struct.pack('!H', len(query)) + query)
            length = struct.unpack('!H', read_exact(sock, 2))[0]
            response = read_exact(sock, length)
        ident, flags, questions, answers, _, _ = struct.unpack('!6H', response[:12])
        assert ident == 0x1234 and flags & 0x8000 and flags & 0xF == 0, response
        assert answers > 0, response
        print('DNS OK', transport.name, flush=True)

# The alias must not expose other ports, including DNS-over-TLS (which pasta
# can also translate). Loopback/LAN attempts must still hit the blacklist.
for address, port in [(resolver, 80), (resolver, 853), ('127.0.0.1', 18080), ('192.168.1.1', 80)]:
    af = socket.AF_INET6 if ':' in address else socket.AF_INET
    with socket.socket(af, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.3)
        result = sock.connect_ex((address, port))
        assert result in (errno.EAGAIN, errno.ETIMEDOUT), (address, port, result)
        print('BLOCKED', address, port, flush=True)

# A real public HTTPS connection must still work through normal libc DNS.
import urllib.request
with urllib.request.urlopen('https://example.com/', timeout=15) as response:
    assert response.status == 200
print('HTTPS OK', flush=True)
'''


@pytest.mark.skipif(
    os.environ.get("BUI_TEST_HOST_DNS") != "1",
    reason="Set BUI_TEST_HOST_DNS=1 to also test the host resolver and public HTTPS",
)
def test_untrusted_with_host_dns_and_https(untrusted_config, tmp_path):
    host = subprocess.run(
        [sys.executable, "-c", DNS_CHECK.split("# The alias must")[0]],
        text=True, capture_output=True, timeout=20,
    )
    assert host.returncode == 0, "Host DNS preflight failed: " + host.stdout + host.stderr
    nf = untrusted_config.network_filter
    dns = read_dns_forwarding()
    iptables, ip6tables, multicall = validate_filtering_requirements(nf)
    # This test does not need a persistent home or installation state.
    untrusted_config.overlays = []
    untrusted_config.command = ["python3", "-c", DNS_CHECK]
    wrapper = create_wrapper_script(
        nf, untrusted_config.build_command(), iptables, ip6tables, multicall,
        tmp_path, dns_forwarding=dns,
    )
    log = tmp_path / "pasta.log"
    args = generate_pasta_args(nf, dns_forwarding=dns)
    args.remove("--quiet")
    command = args + ["--debug", "--log-file", str(log), "--log-size", "1048576", "--", "/bin/sh", str(wrapper)]
    result = subprocess.run(command, text=True, capture_output=True, timeout=45)
    assert result.returncode == 0, result.stdout + result.stderr + log.read_text()
    assert "DNS OK SOCK_DGRAM" in result.stdout
    assert "DNS OK SOCK_STREAM" in result.stdout
    assert "HTTPS OK" in result.stdout
    assert sum(line.startswith("BLOCKED ") for line in result.stdout.splitlines()) == 4


@pytest.mark.parametrize("upstream", ["127.0.0.53", "::1"])
@pytest.mark.parametrize("hostname_filter", [False, True])
def test_untrusted_with_controlled_host_resolver(untrusted_config, tmp_path, upstream, hostname_filter):
    host_resolv = tmp_path / "host-resolv.conf"
    host_resolv.write_text(f"nameserver {upstream}\n")
    dns = read_dns_forwarding(host_resolv)
    if hostname_filter:
        untrusted_config.network.hostname_mode = "whitelist"
        untrusted_config.network.hostname_hosts = ["example.com"]
    nf = untrusted_config.network_filter
    iptables, ip6tables, multicall = validate_filtering_requirements(nf)
    untrusted_config.overlays = []
    check = DNS_CHECK.split("# A real public")[0]
    if hostname_filter:
        # The existing hostname proxy supports UDP. Direct pasta forwarding
        # must support both transports; test its TCP path in the other cases.
        check = check.replace(
            "(socket.SOCK_DGRAM, socket.SOCK_STREAM)", "(socket.SOCK_DGRAM,)",
        )
        check += r'''
blocked = query.replace(b'\x07example', b'\x07blocked')
with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
    sock.settimeout(5)
    sock.sendto(blocked, (resolver, 53))
    response = sock.recv(65535)
    assert response[3] & 0xF == 3, response
print('HOSTNAME BLOCKED', flush=True)
'''
    untrusted_config.command = ["python3", "-c", check]
    wrapper = create_wrapper_script(
        nf, untrusted_config.build_command(), iptables, ip6tables, multicall,
        tmp_path, dns_forwarding=dns,
    )
    inner = generate_pasta_args(nf, dns_forwarding=dns) + ["--", "/bin/sh", str(wrapper)]
    # Both DNS listeners and all firewall changes live in disposable rootless
    # namespaces. Explicit routes make the test independent of host IPv6 and
    # WAN connectivity. No ports are published to the real host.
    fixture = Path(__file__).parent / "helpers" / "dns_server.py"
    outer = [
        "pasta", "--config-net", "--quiet",
        "-a", "192.0.2.2/24", "-g", "192.0.2.1",
        "-a", "fd00:1::2/64", "-g", "fd00:1::1",
        "-t", "none", "-u", "none", "-T", "none", "-U", "none",
        "--", "/bin/sh", "-c", 'exec "$@"', "bui-dns-test",
        str(Path(sys.executable).resolve()), str(fixture), upstream,
    ]
    result = subprocess.run(outer + inner, text=True, capture_output=True, timeout=45)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "DNS OK SOCK_DGRAM" in result.stdout
    if hostname_filter:
        assert "HOSTNAME BLOCKED" in result.stdout
    else:
        assert "DNS OK SOCK_STREAM" in result.stdout
    assert sum(line.startswith("BLOCKED ") for line in result.stdout.splitlines()) == 4
