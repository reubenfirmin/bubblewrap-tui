"""Integration tests for seccomp-based user namespace blocking.

These tests verify that seccomp filtering works correctly in combination
with network filtering in real sandbox execution.
"""

from __future__ import annotations

import json
import os
import subprocess
import uuid
from pathlib import Path

import pytest

# Skip all tests if bwrap or pasta not available
pytestmark = [
    pytest.mark.skipif(
        not Path("/usr/bin/bwrap").exists() and not Path("/bin/bwrap").exists(),
        reason="bwrap not installed",
    ),
]

# Profile directory
PROFILE_DIR = Path.home() / ".config" / "bui" / "profiles"


def run_bui(profile_config: dict, command: list[str], timeout: int = 30) -> tuple[int, str, str]:
    """Run bui with a temporary profile and return exit code, stdout, stderr.

    Args:
        profile_config: The profile configuration dict
        command: Command to run in the sandbox
        timeout: Timeout in seconds

    Returns:
        Tuple of (exit_code, stdout, stderr)
    """
    # Create temporary profile with unique name
    profile_name = f"_test_{uuid.uuid4().hex[:8]}"
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    profile_path = PROFILE_DIR / f"{profile_name}.json"

    try:
        with open(profile_path, 'w') as f:
            json.dump(profile_config, f)

        # Get the bui script path
        bui_path = Path(__file__).parent.parent / "bui"
        if not bui_path.exists():
            pytest.skip("bui not built - run ./build.py first")

        result = subprocess.run(
            [str(bui_path), "--profile", profile_name, "--"] + command,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return result.returncode, result.stdout, result.stderr
    finally:
        if profile_path.exists():
            profile_path.unlink()


def make_profile(
    seccomp_block_userns: bool = False,
    disable_userns: bool = False,
    network_filter: bool = False,
) -> dict:
    """Create a minimal profile configuration.

    Args:
        seccomp_block_userns: Enable seccomp-based user namespace blocking
        disable_userns: Enable bwrap's --disable-userns (incompatible with network filter)
        network_filter: Enable network filtering (requires pasta)

    Returns:
        Profile configuration dict
    """
    profile = {
        "bound_dirs": [
            {"path": "/usr", "readonly": True},
            {"path": "/bin", "readonly": True},
            {"path": "/lib", "readonly": True},
            {"path": "/lib64", "readonly": True},
            {"path": "/sbin", "readonly": True},
        ],
        "overlays": [],
        "drop_caps": [],
        "_vfs_group": {
            "_values": {
                "dev_mode": "minimal",
                "mount_proc": True,
                "mount_tmp": True,
                "tmpfs_size": "",
            }
        },
        "_user_group": {
            "_values": {
                "unshare_user": True,
                "uid": 1000,
                "gid": 1000,
                "username": "testuser",
                "synthetic_passwd": True,
            }
        },
        "_isolation_group": {
            "_values": {
                "unshare_pid": True,
                "unshare_ipc": True,
                "unshare_cgroup": False,
                "disable_userns": disable_userns,
                "seccomp_block_userns": seccomp_block_userns,
            }
        },
        "_hostname_group": {
            "_values": {
                "unshare_uts": True,
                "custom_hostname": "sandbox",
            }
        },
        "_process_group": {
            "_values": {
                "die_with_parent": True,
                "new_session": True,
                "as_pid_1": False,
                "chdir": "",
            }
        },
        "_network_group": {
            "_values": {
                "share_net": True,
                "bind_resolv_conf": True,
                "bind_ssl_certs": True,
            }
        },
        "_desktop_group": {
            "_values": {
                "allow_dbus": False,
                "allow_display": False,
                "bind_user_config": False,
            }
        },
        "_environment_group": {
            "_values": {
                "clear_env": True,
                "keep_env_vars": ["TERM"],
                "unset_env_vars": [],
                "custom_env_vars": {
                    "HOME": "/tmp",
                    "PATH": "/usr/local/bin:/usr/bin:/bin:/usr/local/sbin:/usr/sbin:/sbin",
                },
            }
        },
        "network_filter": {
            "mode": "off",
            "ip_filter": {"mode": "off", "cidrs": []},
            "hostname_filter": {"mode": "off", "hostnames": []},
        },
    }

    if network_filter:
        profile["network_filter"] = {
            "mode": "filter",
            "ip_filter": {
                "mode": "blacklist",
                "cidrs": ["10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"],
            },
            "hostname_filter": {
                "mode": "off",
                "hostnames": [],
            },
        }

    return profile


class TestSeccompConstrainedWithNetworkFilter:
    """Tests for seccomp blocking WITH network filtering enabled."""

    @pytest.mark.skipif(
        not Path("/usr/bin/pasta").exists(),
        reason="pasta not installed (required for network filtering)",
    )
    def test_unshare_user_blocked(self):
        """unshare --user should fail when seccomp is enabled with network filter."""
        profile = make_profile(seccomp_block_userns=True, network_filter=True)

        exit_code, stdout, stderr = run_bui(
            profile,
            ["/bin/sh", "-c", "unshare --user echo SUCCESS 2>&1 || echo BLOCKED"],
        )

        output = stdout + stderr
        assert "BLOCKED" in output or "Operation not permitted" in output
        assert "SUCCESS" not in output

    @pytest.mark.skipif(
        not Path("/usr/bin/pasta").exists(),
        reason="pasta not installed (required for network filtering)",
    )
    def test_regular_commands_work(self):
        """Regular commands should work normally with seccomp + network filter."""
        profile = make_profile(seccomp_block_userns=True, network_filter=True)

        exit_code, stdout, stderr = run_bui(
            profile,
            ["/bin/sh", "-c", "echo HELLO_WORLD; id"],
        )

        output = stdout + stderr
        assert "HELLO_WORLD" in output

    @pytest.mark.skipif(
        not Path("/usr/bin/pasta").exists(),
        reason="pasta not installed (required for network filtering)",
    )
    def test_clone_without_newuser_works(self):
        """clone() without CLONE_NEWUSER should still work (e.g., fork)."""
        profile = make_profile(seccomp_block_userns=True, network_filter=True)

        # Running a subshell uses fork/clone without CLONE_NEWUSER
        exit_code, stdout, stderr = run_bui(
            profile,
            ["/bin/sh", "-c", "(echo SUBSHELL_WORKS)"],
        )

        output = stdout + stderr
        assert "SUBSHELL_WORKS" in output


class TestSeccompConstrainedWithoutNetworkFilter:
    """Tests for seccomp blocking WITHOUT network filtering.

    Note: seccomp_block_userns is specifically designed for use with network filtering
    to avoid the CAP_NET_ADMIN conflict with bwrap's --disable-userns.
    Without network filtering, you should use disable_userns=True instead.
    """

    def test_disable_userns_blocks_without_network_filter(self):
        """unshare --user should fail when disable_userns is enabled without network filter.

        Without network filtering, use bwrap's --disable-userns (not seccomp).
        """
        profile = make_profile(seccomp_block_userns=False, disable_userns=True, network_filter=False)

        exit_code, stdout, stderr = run_bui(
            profile,
            ["/bin/sh", "-c", "unshare --user echo SUCCESS 2>&1 || echo BLOCKED"],
        )

        output = stdout + stderr
        assert "BLOCKED" in output or "Operation not permitted" in output
        assert "SUCCESS" not in output

    def test_seccomp_alone_does_not_block_without_network_filter(self):
        """seccomp_block_userns alone (without network filter) does not block.

        This is expected behavior: seccomp is only applied via the network filter's
        init script. Without network filtering, use disable_userns=True instead.
        """
        profile = make_profile(seccomp_block_userns=True, disable_userns=False, network_filter=False)

        exit_code, stdout, stderr = run_bui(
            profile,
            ["/bin/sh", "-c", "unshare --user echo SUCCESS 2>&1 || echo BLOCKED"],
        )

        output = stdout + stderr
        # Without network filtering, seccomp isn't applied (it's in the init.sh script)
        # So unshare --user succeeds (unless system blocks it via sysctl)
        if "Operation not permitted" in output:
            pytest.skip("System blocks unprivileged user namespaces via sysctl")
        assert "SUCCESS" in output

    def test_regular_commands_work(self):
        """Regular commands should work normally."""
        profile = make_profile(seccomp_block_userns=True, network_filter=False)

        exit_code, stdout, stderr = run_bui(
            profile,
            ["/bin/sh", "-c", "echo HELLO_WORLD; id"],
        )

        output = stdout + stderr
        assert "HELLO_WORLD" in output

    def test_clone_without_newuser_works(self):
        """clone() without CLONE_NEWUSER should still work."""
        profile = make_profile(seccomp_block_userns=True, network_filter=False)

        exit_code, stdout, stderr = run_bui(
            profile,
            ["/bin/sh", "-c", "(echo SUBSHELL_WORKS)"],
        )

        output = stdout + stderr
        assert "SUBSHELL_WORKS" in output


class TestUnconstrainedWithNetworkFilter:
    """Tests for NO seccomp blocking WITH network filtering."""

    @pytest.mark.skipif(
        not Path("/usr/bin/pasta").exists(),
        reason="pasta not installed (required for network filtering)",
    )
    def test_unshare_user_allowed(self):
        """unshare --user should succeed when seccomp is disabled."""
        profile = make_profile(seccomp_block_userns=False, disable_userns=False, network_filter=True)

        exit_code, stdout, stderr = run_bui(
            profile,
            ["/bin/sh", "-c", "unshare --user echo SUCCESS 2>&1 || echo BLOCKED"],
        )

        output = stdout + stderr
        # Without seccomp, unshare --user should work
        assert "SUCCESS" in output or "BLOCKED" not in output.replace("Operation not permitted", "")

    @pytest.mark.skipif(
        not Path("/usr/bin/pasta").exists(),
        reason="pasta not installed (required for network filtering)",
    )
    def test_regular_commands_work(self):
        """Regular commands should work with network filter only."""
        profile = make_profile(seccomp_block_userns=False, network_filter=True)

        exit_code, stdout, stderr = run_bui(
            profile,
            ["/bin/sh", "-c", "echo HELLO_WORLD"],
        )

        output = stdout + stderr
        assert "HELLO_WORLD" in output


class TestUnconstrainedWithoutNetworkFilter:
    """Tests for NO seccomp blocking and NO network filtering (minimal sandbox)."""

    def test_unshare_user_allowed(self):
        """unshare --user should succeed in minimal sandbox."""
        profile = make_profile(seccomp_block_userns=False, disable_userns=False, network_filter=False)

        exit_code, stdout, stderr = run_bui(
            profile,
            ["/bin/sh", "-c", "unshare --user echo SUCCESS 2>&1 || echo BLOCKED"],
        )

        output = stdout + stderr
        # In a minimal sandbox without restrictions, unshare --user should work
        # (assuming the system allows unprivileged user namespaces)
        # Note: Some systems have this disabled via sysctl
        if "Operation not permitted" in output:
            pytest.skip("System does not allow unprivileged user namespaces (sysctl restriction)")
        assert "SUCCESS" in output

    def test_regular_commands_work(self):
        """Regular commands should work in minimal sandbox."""
        profile = make_profile(seccomp_block_userns=False, network_filter=False)

        exit_code, stdout, stderr = run_bui(
            profile,
            ["/bin/sh", "-c", "echo HELLO_WORLD"],
        )

        output = stdout + stderr
        assert "HELLO_WORLD" in output

    def test_subshell_works(self):
        """Subshells should work in minimal sandbox."""
        profile = make_profile(seccomp_block_userns=False, network_filter=False)

        exit_code, stdout, stderr = run_bui(
            profile,
            ["/bin/sh", "-c", "(echo SUBSHELL_WORKS)"],
        )

        output = stdout + stderr
        assert "SUBSHELL_WORKS" in output


class TestAutoEnableSeccomp:
    """Tests for automatic seccomp enabling when network filter + disable_userns conflict."""

    @pytest.mark.skipif(
        not Path("/usr/bin/pasta").exists(),
        reason="pasta not installed (required for network filtering)",
    )
    def test_auto_enables_seccomp_for_conflict(self):
        """When network filter + disable_userns are both set, seccomp should be auto-enabled."""
        # This profile has the conflict: network filter needs CAP_NET_ADMIN,
        # but disable_userns would prevent it. The system should auto-enable seccomp.
        profile = make_profile(
            seccomp_block_userns=False,  # Not explicitly enabled
            disable_userns=True,  # Would conflict with network filter
            network_filter=True,
        )

        exit_code, stdout, stderr = run_bui(
            profile,
            ["/bin/sh", "-c", "unshare --user echo SUCCESS 2>&1 || echo BLOCKED"],
        )

        output = stdout + stderr
        # Seccomp should have been auto-enabled, blocking unshare --user
        assert "BLOCKED" in output or "Operation not permitted" in output
        assert "SUCCESS" not in output
