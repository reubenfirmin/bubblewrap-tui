"""Opt-in offline isolation checks: BUI_TEST_NETWORK=1 uv run ... pytest this file.

Requires bubblewrap and rootless user/network namespaces. Only controlled
loopback and abstract Unix listeners are used; no DNS or internet is needed.
"""

import errno
import os
import socket
import subprocess
import uuid

import pytest

from command_execution import execute_sandbox
from profiles import Profile
from virtual_files import create_virtual_files


pytestmark = pytest.mark.skipif(
    os.environ.get("BUI_TEST_NETWORK") != "1",
    reason="Set BUI_TEST_NETWORK=1 to exercise real rootless network isolation",
)


@pytest.fixture(params=["ipv4", "ipv6", "abstract"])
def host_listener(request):
    family, address = {
        "ipv4": (socket.AF_INET, ("127.0.0.1", 0)),
        "ipv6": (socket.AF_INET6, ("::1", 0)),
        "abstract": (socket.AF_UNIX, "\0bui-network-test-" + uuid.uuid4().hex),
    }[request.param]
    try:
        listener = socket.socket(family, socket.SOCK_STREAM)
    except OSError as exc:
        if family == socket.AF_INET6 and exc.errno == errno.EAFNOSUPPORT:
            pytest.skip("Host does not support IPv6")
        raise
    with listener:
        try:
            listener.bind(address)
        except OSError as exc:
            if family == socket.AF_INET6 and exc.errno == errno.EADDRNOTAVAIL:
                pytest.skip("Host has no IPv6 loopback address")
            raise
        listener.listen(8)
        yield family, listener.getsockname()


@pytest.mark.parametrize("mode", ["off", "filter"])
def test_offline_profile_blocks_host_listeners(
    untrusted_config, tmp_path, monkeypatch, host_listener, mode,
):
    family, address = host_listener

    def host_control():
        with socket.socket(family, socket.SOCK_STREAM) as client:
            client.settimeout(2)
            client.connect(address)

    # A failed host service must never masquerade as successful isolation.
    host_control()
    config = untrusted_config
    config.overlays = []
    config.network.network_mode = mode
    config.network.ip_mode = "off"
    config.network.ip_cidrs = []
    config.network.bind_resolv_conf = False
    config.network.bind_ssl_certs = False

    def unexpected_pasta(*args, **kwargs):
        pytest.fail("A profile without active filters/audit must not launch pasta")

    monkeypatch.setattr("net.execute_with_network_filter", unexpected_pasta)
    monkeypatch.setattr("net.execute_with_audit", unexpected_pasta)

    results = []

    def run_without_terminal(cmd, seccomp_fd=None):
        # Exercise real dispatch, argument generation, virtual files and seccomp;
        # replace only terminal transport to bound execution time and capture output.
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=15,
                pass_fds=() if seccomp_fd is None else (seccomp_fd,),
            )
            results.append(result)
            return result.returncode
        finally:
            if seccomp_fd is not None:
                os.close(seccomp_fd)

    monkeypatch.setattr("command_execution._run_with_pty", run_without_terminal)
    profile = Profile(tmp_path / "network.json")

    # Positive and negative controls run identical socket code through bwrap.
    # Both are saved/reloaded to cover direct profile execution as well as defaults.
    for share_net in (True, False):
        config.network.share_net = share_net
        config.command = ["python3", "-c", f'''
import socket
with socket.socket({int(family)}, socket.SOCK_STREAM) as client:
    client.settimeout(1)
    try:
        client.connect({address!r})
    except OSError:
        connected = False
    else:
        connected = True
assert connected == {share_net!r}, connected
print("CONNECTED" if connected else "ISOLATED", flush=True)
''']
        profile.save(config)
        loaded, warnings = profile.load(config.command)
        assert warnings == []
        assert ("Full access" if share_net else "Completely offline") in loaded.get_explanation()

        # Keep all generated files in pytest's disposable directory.
        with monkeypatch.context() as scoped:
            scoped.setattr("virtual_files.tempfile.tempdir", str(tmp_path))
            vfiles = create_virtual_files(loaded)
        with pytest.raises(SystemExit) as exc:
            execute_sandbox(
                loaded, vfiles.get_file_map(), lambda cfg, files: cfg.build_command(files),
                None, [], None,
            )
        result = results[-1]
        assert exc.value.code == 0, result.stdout + result.stderr
        assert ("CONNECTED" if share_net else "ISOLATED") in result.stdout

    host_control()
