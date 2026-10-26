"""Regression coverage for installation, updates, and the untrusted profile."""

import hashlib
import io
import json
import os
import sys
from pathlib import Path

import pytest

import installer
from model import SandboxConfig
from model.network_filter import FilterMode, NetworkMode
from model.serializers import network_to_args
from net.iptables import generate_iptables_rules
from profiles import deserialize, serialize


@pytest.fixture
def install_home(tmp_path, monkeypatch):
    home = tmp_path / "home"
    local_bin = home / ".local" / "bin"
    local_bin.mkdir(parents=True)
    (home / ".config" / "bui" / "profiles").mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("PATH", f"{local_bin}{os.pathsep}{os.environ.get('PATH', '')}")
    return home


def mock_release(monkeypatch, content, checksum=None):
    responses = {
        installer.BUI_API_URL: b'{"tag_name": "v9.9.9"}',
        installer.BUI_RELEASE_URL: content,
        installer.BUI_CHECKSUM_URL: (
            f"{checksum or hashlib.sha256(content).hexdigest()}  bui\n".encode()
        ),
    }

    def urlopen(request, **kwargs):
        url = request if isinstance(request, str) else request.full_url
        return io.BytesIO(responses[url])

    monkeypatch.setattr(installer.urllib.request, "urlopen", urlopen)


@pytest.mark.parametrize("source_kind", ["installed", "symlink", "hardlink", "download"])
def test_install_refreshes_profile_even_from_installed_file(
    install_home, tmp_path, monkeypatch, source_kind
):
    install_path = install_home / ".local" / "bin" / "bui"
    install_path.write_text("existing executable\n")
    profiles_dir = install_home / ".config" / "bui" / "profiles"
    (profiles_dir / "untrusted.json").write_text("{}")
    custom_profile = profiles_dir / "custom.json"
    custom_profile.write_text('{"custom": true}')

    source_path = tmp_path / "source.py"
    if source_kind == "installed":
        monkeypatch.setattr(installer, "__file__", str(install_path))
        source_path = None
    elif source_kind == "symlink":
        source_path.symlink_to(install_path)
    elif source_kind == "hardlink":
        source_path.hardlink_to(install_path)
    else:
        source_path.write_text("downloaded executable\n")

    installer.do_install("9.9.9", source_path)

    expected = "downloaded executable\n" if source_kind == "download" else "existing executable\n"
    assert install_path.read_text() == expected
    assert install_path.stat().st_mode & 0o777 == 0o755
    profile = deserialize(SandboxConfig, json.loads((profiles_dir / "untrusted.json").read_text()))
    assert profile.network_filter.requires_pasta()
    assert profile.network_filter.ip_filter.mode == FilterMode.BLACKLIST
    assert custom_profile.read_text() == '{"custom": true}'


def test_update_uses_downloaded_versions_profile(install_home, monkeypatch, capfd):
    profiles_dir = install_home / ".config" / "bui" / "profiles"
    (profiles_dir / "untrusted.json").write_text("{}")
    custom_profile = profiles_dir / "custom.json"
    custom_profile.write_text('{"custom": true}')

    # Simulate a newer release with a changed built-in profile. Run its real
    # installer in a child process so the running updater cannot supply defaults.
    new_installer = Path(installer.__file__).read_text().replace(
        '"custom_hostname": "sandbox"', '"custom_hostname": "updated-sandbox"'
    )
    content = (
        f"#!{sys.executable}\n" + new_installer
        + '\nif __name__ == "__main__":\n    do_install("9.9.9")\n'
    ).encode()
    mock_release(monkeypatch, content)

    installer.do_update("0.0.1")

    assert (install_home / ".local" / "bin" / "bui").read_bytes() == content
    profile_data = json.loads((profiles_dir / "untrusted.json").read_text())
    assert profile_data["_hostname_group"]["_values"]["custom_hostname"] == "updated-sandbox"
    assert deserialize(SandboxConfig, profile_data).network_filter.requires_pasta()
    assert custom_profile.read_text() == '{"custom": true}'
    assert "Installed bui v9.9.9" in capfd.readouterr().out


@pytest.mark.parametrize("failure", ["checksum", "installer"])
def test_failed_update_leaves_existing_install_and_profile(
    install_home, monkeypatch, capfd, failure
):
    install_path = install_home / ".local" / "bin" / "bui"
    install_path.write_text("existing executable\n")
    profile_path = install_home / ".config" / "bui" / "profiles" / "untrusted.json"
    profile_path.write_text('{"existing": true}')
    content = f"#!{sys.executable}\nraise SystemExit(23)\n".encode()
    mock_release(monkeypatch, content, "bad-checksum" if failure == "checksum" else None)

    with pytest.raises(SystemExit) as exc:
        installer.do_update("0.0.1")

    assert exc.value.code == 1
    assert install_path.read_text() == "existing executable\n"
    assert profile_path.read_text() == '{"existing": true}'
    error = "Checksum verification failed" if failure == "checksum" else "Error installing update"
    assert error in capfd.readouterr().err


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
