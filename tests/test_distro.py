"""Tests for distro module."""

from unittest.mock import patch

import pytest

from distro import (
    DistroConfig,
    detect_distro_id,
    get_current_distro,
    get_distro_by_id,
    list_supported_distros,
)
from distro.fedora import FedoraDistro
from distro.debian import DebianDistro
from distro.arch import ArchDistro
from distro.generic import GenericDistro


class TestDetectDistroId:
    """Test detect_distro_id function."""

    @patch("distro.detector.Path.exists")
    def test_returns_none_when_no_os_release(self, mock_exists):
        """Returns None when /etc/os-release doesn't exist."""
        mock_exists.return_value = False
        assert detect_distro_id() is None

    @patch("distro.detector.Path.read_text")
    @patch("distro.detector.Path.exists")
    def test_detects_fedora(self, mock_exists, mock_read):
        """Detects Fedora distribution."""
        mock_exists.return_value = True
        mock_read.return_value = 'NAME="Fedora Linux"\nID=fedora\nVERSION_ID=39'
        assert detect_distro_id() == "fedora"

    @patch("distro.detector.Path.read_text")
    @patch("distro.detector.Path.exists")
    def test_detects_ubuntu(self, mock_exists, mock_read):
        """Detects Ubuntu distribution."""
        mock_exists.return_value = True
        mock_read.return_value = 'NAME="Ubuntu"\nID=ubuntu\nVERSION_ID="22.04"'
        assert detect_distro_id() == "ubuntu"

    @patch("distro.detector.Path.read_text")
    @patch("distro.detector.Path.exists")
    def test_handles_quoted_id(self, mock_exists, mock_read):
        """Handles quoted ID values."""
        mock_exists.return_value = True
        mock_read.return_value = 'ID="arch"'
        assert detect_distro_id() == "arch"


class TestGetDistroById:
    """Test get_distro_by_id function."""

    def test_returns_fedora_for_fedora(self):
        """Returns FedoraDistro for 'fedora' ID."""
        distro = get_distro_by_id("fedora")
        assert isinstance(distro, FedoraDistro)

    def test_returns_fedora_for_rhel_alias(self):
        """Returns FedoraDistro for 'rhel' alias."""
        distro = get_distro_by_id("rhel")
        assert isinstance(distro, FedoraDistro)

    def test_returns_debian_for_ubuntu_alias(self):
        """Returns DebianDistro for 'ubuntu' alias."""
        distro = get_distro_by_id("ubuntu")
        assert isinstance(distro, DebianDistro)

    def test_returns_arch_for_manjaro_alias(self):
        """Returns ArchDistro for 'manjaro' alias."""
        distro = get_distro_by_id("manjaro")
        assert isinstance(distro, ArchDistro)

    def test_returns_none_for_unknown(self):
        """Returns None for unknown distribution."""
        distro = get_distro_by_id("unknown_distro")
        assert distro is None

    def test_case_insensitive(self):
        """ID lookup is case insensitive."""
        distro = get_distro_by_id("FEDORA")
        assert isinstance(distro, FedoraDistro)


class TestGetCurrentDistro:
    """Test get_current_distro function."""

    @patch("distro.detector.detect_distro_id")
    def test_returns_detected_distro(self, mock_detect):
        """Returns detected distro when recognized."""
        mock_detect.return_value = "fedora"
        distro = get_current_distro()
        assert isinstance(distro, FedoraDistro)

    @patch("distro.detector.detect_distro_id")
    def test_returns_generic_for_unknown(self, mock_detect):
        """Returns GenericDistro for unknown distributions."""
        mock_detect.return_value = "unknown_distro"
        distro = get_current_distro()
        assert isinstance(distro, GenericDistro)

    @patch("distro.detector.detect_distro_id")
    def test_returns_generic_when_detection_fails(self, mock_detect):
        """Returns GenericDistro when detection fails."""
        mock_detect.return_value = None
        distro = get_current_distro()
        assert isinstance(distro, GenericDistro)


class TestListSupportedDistros:
    """Test list_supported_distros function."""

    def test_returns_list_of_strings(self):
        """Returns a list of strings."""
        distros = list_supported_distros()
        assert isinstance(distros, list)
        assert all(isinstance(d, str) for d in distros)

    def test_includes_major_distros(self):
        """Includes major distributions."""
        distros = list_supported_distros()
        assert "fedora" in distros
        assert "debian" in distros
        assert "arch" in distros

    def test_sorted(self):
        """Returns sorted list."""
        distros = list_supported_distros()
        assert distros == sorted(distros)


class TestFedoraDistro:
    """Test FedoraDistro configuration."""

    def test_name(self):
        """Has correct name."""
        distro = FedoraDistro()
        assert distro.name == "fedora"

    def test_package_manager(self):
        """Uses dnf package manager."""
        distro = FedoraDistro()
        assert distro.package_manager == "dnf"

    def test_install_command(self):
        """Generates correct install command."""
        distro = FedoraDistro()
        cmd = distro.get_install_command("passt")
        assert cmd == "sudo dnf install passt"

    def test_ssl_cert_paths(self):
        """Returns SSL cert paths."""
        distro = FedoraDistro()
        paths = distro.get_ssl_cert_paths()
        assert "/etc/pki/tls/certs" in paths

    def test_aliases_include_rhel(self):
        """Aliases include RHEL variants."""
        assert "rhel" in FedoraDistro.aliases
        assert "centos" in FedoraDistro.aliases
        assert "rocky" in FedoraDistro.aliases


class TestDebianDistro:
    """Test DebianDistro configuration."""

    def test_name(self):
        """Has correct name."""
        distro = DebianDistro()
        assert distro.name == "debian"

    def test_package_manager(self):
        """Uses apt package manager."""
        distro = DebianDistro()
        assert distro.package_manager == "apt"

    def test_install_command(self):
        """Generates correct install command."""
        distro = DebianDistro()
        cmd = distro.get_install_command("passt")
        assert cmd == "sudo apt install passt"

    def test_ssl_cert_paths(self):
        """Returns SSL cert paths."""
        distro = DebianDistro()
        paths = distro.get_ssl_cert_paths()
        assert "/etc/ssl/certs" in paths

    def test_aliases_include_ubuntu(self):
        """Aliases include Ubuntu variants."""
        assert "ubuntu" in DebianDistro.aliases
        assert "linuxmint" in DebianDistro.aliases


class TestArchDistro:
    """Test ArchDistro configuration."""

    def test_name(self):
        """Has correct name."""
        distro = ArchDistro()
        assert distro.name == "arch"

    def test_package_manager(self):
        """Uses pacman package manager."""
        distro = ArchDistro()
        assert distro.package_manager == "pacman"

    def test_install_command(self):
        """Generates correct install command."""
        distro = ArchDistro()
        cmd = distro.get_install_command("passt")
        assert cmd == "sudo pacman -S passt"

    def test_aliases_include_manjaro(self):
        """Aliases include Manjaro."""
        assert "manjaro" in ArchDistro.aliases


class TestGenericDistro:
    """Test GenericDistro fallback configuration."""

    def test_name(self):
        """Has 'generic' name."""
        distro = GenericDistro()
        assert distro.name == "generic"

    @patch("shutil.which")
    def test_detects_apt(self, mock_which):
        """Detects apt package manager."""
        mock_which.side_effect = lambda x: "/usr/bin/apt" if x == "apt" else None
        distro = GenericDistro()
        cmd = distro.get_install_command("passt")
        assert "apt install" in cmd

    @patch("shutil.which")
    def test_detects_dnf(self, mock_which):
        """Detects dnf package manager."""
        mock_which.side_effect = lambda x: "/usr/bin/dnf" if x == "dnf" else None
        distro = GenericDistro()
        cmd = distro.get_install_command("passt")
        assert "dnf install" in cmd

    @patch("shutil.which")
    def test_fallback_message(self, mock_which):
        """Returns fallback message when no package manager found."""
        mock_which.return_value = None
        distro = GenericDistro()
        cmd = distro.get_install_command("passt")
        assert "Install passt" in cmd


class TestGenerateInstallableProfile:
    """Test profile generation."""

    def test_returns_dict(self):
        """Returns a dictionary."""
        distro = FedoraDistro()
        profile = distro.generate_installable_profile()
        assert isinstance(profile, dict)

    def test_has_bound_dirs(self):
        """Profile has bound_dirs."""
        distro = FedoraDistro()
        profile = distro.generate_installable_profile()
        assert "bound_dirs" in profile
        assert isinstance(profile["bound_dirs"], list)

    def test_has_overlays(self):
        """Profile has overlays."""
        distro = FedoraDistro()
        profile = distro.generate_installable_profile()
        assert "overlays" in profile
        assert len(profile["overlays"]) > 0
        assert profile["overlays"][0]["dest"] == "/home/sandbox"
        assert profile["overlays"][0]["mode"] == "persistent"

    def test_has_network_filter(self):
        """Profile has network_filter configuration."""
        distro = FedoraDistro()
        profile = distro.generate_installable_profile()
        assert "network_filter" in profile
        assert "mode" in profile["network_filter"]

    def test_is_json_serializable(self):
        """Profile is JSON serializable."""
        import json
        distro = FedoraDistro()
        profile = distro.generate_installable_profile()
        # Should not raise
        json.dumps(profile)
