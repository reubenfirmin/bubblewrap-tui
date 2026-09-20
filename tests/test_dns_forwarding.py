"""Host DNS forwarding and launch-path regressions for filtered sandboxes."""

import shlex
from pathlib import Path
from unittest.mock import Mock

import pytest

from model.network_filter import FilterMode
from model.serializers import network_to_args
from net.dns_forward import DNSConfigurationError, read_dns_forwarding
from net.iptables import generate_iptables_rules
from net.pasta_args import generate_pasta_args
from net.pasta_exec import execute_with_pasta


def forwarding_from_text(tmp_path, content):
    path = tmp_path / "host-resolv.conf"
    path.write_text(content)
    return read_dns_forwarding(path)


@pytest.mark.parametrize("upstream", ["127.0.0.53", "192.168.1.1", "9.9.9.9", "::1", "fd12::1"])
def test_maps_host_resolver_in_its_own_address_family(tmp_path, upstream):
    dns = forwarding_from_text(tmp_path, f"nameserver {upstream}\n")
    address, host = dns.servers[0]
    assert host == upstream
    assert (":" in address) == (":" in upstream)
    assert address != upstream
    assert f"nameserver {address}\n" in dns.resolv_conf()


def test_preserves_search_options_and_first_resolver_per_family(tmp_path):
    dns = forwarding_from_text(tmp_path, """# host config
nameserver 127.0.0.53 # local stub
nameserver 1.1.1.1
nameserver ::1
nameserver 2001:4860:4860::8888
search vpn.example example.org
options edns0 timeout:2
""")
    assert [host for _, host in dns.servers] == ["127.0.0.53", "::1"]
    assert "search vpn.example example.org\n" in dns.resolv_conf()
    assert "options edns0 timeout:2\n" in dns.resolv_conf()
    assert "nameserver 1.1.1.1" not in dns.resolv_conf()


@pytest.mark.parametrize("content", [
    "", "search example.org\n", "nameserver\n", "nameserver invalid\n",
    "nameserver 0.0.0.0\n", "nameserver 224.0.0.1\n",
    "nameserver fe80::1%eth0\n", "nameserver $(touch /tmp/dns-injection)\n",
])
def test_invalid_or_missing_resolvers_fail_without_public_fallback(tmp_path, content):
    with pytest.raises(DNSConfigurationError):
        forwarding_from_text(tmp_path, content)


def test_unreadable_resolv_conf_fails_clearly(tmp_path):
    with pytest.raises(DNSConfigurationError, match="Cannot read host DNS"):
        read_dns_forwarding(tmp_path / "missing")


def test_dns_exception_precedes_private_blocks_and_is_port_scoped(tmp_path, untrusted_config):
    dns = forwarding_from_text(tmp_path, "nameserver 127.0.0.53\nnameserver ::1\n")
    nf = untrusted_config.network_filter
    v4, v6 = generate_iptables_rules(nf, dns)
    for address, _ in dns.servers:
        rules, tool, cidr = (v6, "ip6tables", "fc00::/7") if ":" in address else (v4, "iptables", "169.254.0.0/16")
        alias_drop = rules.index(f"{tool} -A OUTPUT -d {address} -j DROP")
        network_drop = rules.index(f"{tool} -A OUTPUT -d {cidr} -j DROP")
        for protocol in ("udp", "tcp"):
            allow = rules.index(f"{tool} -A OUTPUT -d {address} -p {protocol} --dport 53 -j ACCEPT")
            assert allow < alias_drop < network_drop
        assert not any(f"-d {address} -j ACCEPT" in rule for rule in rules)
    assert "iptables -A OUTPUT -d 127.0.0.0/8 -j DROP" in v4
    assert "iptables -A OUTPUT -d 192.168.0.0/16 -j DROP" in v4
    args = generate_pasta_args(nf, dns_forwarding=dns)
    for address, upstream in dns.servers:
        index = args.index(address)
        assert args[index - 1:index + 3] == ["--dns-forward", address, "--dns-host", upstream]


def test_dns_forwarding_does_not_remove_ip_whitelist(tmp_path, untrusted_config):
    dns = forwarding_from_text(tmp_path, "nameserver 127.0.0.53\n")
    nf = untrusted_config.network_filter
    nf.ip_filter.mode = FilterMode.WHITELIST
    nf.ip_filter.cidrs = ["203.0.113.5/32"]
    v4, v6 = generate_iptables_rules(nf, dns)
    assert v4[-1] == "iptables -A OUTPUT -j DROP"
    assert v6[-1] == "ip6tables -A OUTPUT -j DROP"
    assert "iptables -A OUTPUT -d 203.0.113.5/32 -j ACCEPT" in v4


@pytest.fixture
def launch(monkeypatch, tmp_path):
    import net.pasta_exec as execution

    workdir = tmp_path / "launch"
    workdir.mkdir()
    monkeypatch.setattr("tempfile.mkdtemp", lambda **kwargs: str(workdir))
    monkeypatch.setattr(execution, "validate_filtering_requirements", lambda nf: ("/usr/bin/iptables", "/usr/bin/ip6tables", False))
    run = Mock(return_value=0)
    monkeypatch.setattr(execution, "_run_with_pty", run)
    monkeypatch.setattr("commandoutput.print_execution_header", Mock())
    return workdir, run


def build_network_command(config, file_map):
    return ["bwrap", *network_to_args(config._network_group, config.network_filter), "--", "true"]


@pytest.mark.parametrize("hostname_filter", [False, True])
def test_launch_mounts_generated_resolver_and_forwards_host_dns(
    tmp_path, monkeypatch, untrusted_config, launch, hostname_filter,
):
    dns = forwarding_from_text(tmp_path, "nameserver 127.0.0.53\n")
    monkeypatch.setattr("net.pasta_exec.read_dns_forwarding", lambda: dns)
    monkeypatch.setattr("detection.find_dns_paths", lambda: [
        "/run/systemd/resolve/stub-resolv.conf", "/etc/resolv.conf",
        "/run/systemd/resolve", "/etc/nsswitch.conf",
    ])
    if hostname_filter:
        untrusted_config.network.hostname_mode = "whitelist"
        untrusted_config.network.hostname_hosts = ["example.org"]

    assert execute_with_pasta(untrusted_config, None, build_network_command) == 0
    workdir, run = launch
    command = run.call_args.args[0]
    assert command[command.index("--dns-host") + 1] == "127.0.0.53"
    wrapper = Path(command[-1]).read_text()
    bwrap = shlex.split(next(line for line in wrapper.splitlines() if line.startswith("exec bwrap")))[1:]
    resolver = workdir / "resolv.conf"
    index = bwrap.index(str(resolver))
    assert bwrap[index - 1:index + 2] == ["--ro-bind", str(resolver), "/etc/resolv.conf"]
    assert index < bwrap.index("--")
    assert bwrap.count("/etc/resolv.conf") == 1
    assert "/run/systemd/resolve/stub-resolv.conf" not in bwrap
    assert "/etc/nsswitch.conf" in bwrap
    assert "--share-net" not in bwrap and "--unshare-net" not in bwrap
    assert resolver.stat().st_mode & 0o222 == 0
    address = dns.servers[0][0]
    if hostname_filter:
        assert "nameserver 127.0.0.1" in resolver.read_text()
        proxy = (workdir / "dns_proxy.py").read_text()
        assert f'UPSTREAM_DNS = "{address}"' in proxy
        assert "--sport 53 -m conntrack --ctstate ESTABLISHED -j ACCEPT" in wrapper
    else:
        assert f"nameserver {address}" in resolver.read_text()
        assert not (workdir / "dns_proxy.py").exists()
    assert "-A OUTPUT -d 127.0.0.0/8 -j DROP" in wrapper


def test_no_dns_forwarding_when_dns_is_disabled(monkeypatch, untrusted_config, launch):
    untrusted_config.network.bind_resolv_conf = False
    read = Mock(side_effect=AssertionError("DNS should not be read"))
    monkeypatch.setattr("net.pasta_exec.read_dns_forwarding", read)
    execute_with_pasta(untrusted_config, None, build_network_command)
    workdir, run = launch
    assert not (workdir / "resolv.conf").exists()
    assert "--dns-forward" not in run.call_args.args[0]


def test_missing_dns_stops_before_launch(monkeypatch, untrusted_config, launch, capsys):
    monkeypatch.setattr("net.pasta_exec.read_dns_forwarding", Mock(side_effect=DNSConfigurationError("No DNS nameservers configured on host.")))
    with pytest.raises(SystemExit) as exc:
        execute_with_pasta(untrusted_config, None, build_network_command)
    assert exc.value.code == 1
    launch[1].assert_not_called()
    assert "No DNS nameservers configured" in capsys.readouterr().err


def test_ipv6_dns_requires_ipv6_firewall(tmp_path, monkeypatch, untrusted_config, launch):
    dns = forwarding_from_text(tmp_path, "nameserver ::1\n")
    monkeypatch.setattr("net.pasta_exec.read_dns_forwarding", lambda: dns)
    monkeypatch.setattr("net.pasta_exec.validate_filtering_requirements", lambda nf: ("/usr/bin/iptables", None, False))
    with pytest.raises(SystemExit):
        execute_with_pasta(untrusted_config, None, build_network_command)
    launch[1].assert_not_called()
