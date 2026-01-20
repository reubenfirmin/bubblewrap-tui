"""Network filtering utilities for slirp4netns integration.

Provides functionality for:
- Detecting slirp4netns installation
- Detecting Linux distribution for install instructions
- Generating iptables/ip6tables rules from NetworkFilter config
- Generating slirp4netns command arguments
"""

from __future__ import annotations

import ipaddress
import shutil
import socket
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from model.network_filter import NetworkFilter, FilterMode


def check_slirp4netns() -> bool:
    """Check if slirp4netns is installed."""
    return shutil.which("slirp4netns") is not None


def find_iptables() -> tuple[str | None, str | None, bool]:
    """Find iptables/ip6tables and determine if they're multi-call binaries.

    Returns:
        Tuple of (iptables_real_path, ip6tables_real_path, is_multicall).
        Paths are resolved (following symlinks). is_multicall is True if
        the binary is xtables-nft-multi or similar multi-call binary.
    """
    import os

    def resolve(name: str) -> str | None:
        path = shutil.which(name)
        if path is None:
            return None
        try:
            return os.path.realpath(path)
        except OSError:
            return path

    iptables = resolve("iptables")
    ip6tables = resolve("ip6tables")

    # Check if it's a multi-call binary (like xtables-nft-multi)
    is_multicall = iptables is not None and "multi" in iptables

    return (iptables, ip6tables, is_multicall)


def check_iptables() -> bool:
    """Check if iptables is available."""
    iptables, _, _ = find_iptables()
    return iptables is not None


def detect_distro() -> str | None:
    """Detect Linux distribution from /etc/os-release.

    Returns:
        Distribution ID (e.g., 'fedora', 'ubuntu', 'arch') or None if not detected.
    """
    os_release = Path("/etc/os-release")
    if not os_release.exists():
        return None

    try:
        content = os_release.read_text()
        for line in content.splitlines():
            if line.startswith("ID="):
                return line.split("=", 1)[1].strip().strip('"').lower()
    except OSError:
        pass
    return None


def get_install_instructions() -> str:
    """Return distro-specific install instructions for slirp4netns."""
    distro = detect_distro()

    instructions = {
        "fedora": "sudo dnf install slirp4netns",
        "rhel": "sudo dnf install slirp4netns",
        "centos": "sudo dnf install slirp4netns",
        "debian": "sudo apt install slirp4netns",
        "ubuntu": "sudo apt install slirp4netns",
        "arch": "sudo pacman -S slirp4netns",
        "manjaro": "sudo pacman -S slirp4netns",
        "opensuse": "sudo zypper install slirp4netns",
        "opensuse-leap": "sudo zypper install slirp4netns",
        "opensuse-tumbleweed": "sudo zypper install slirp4netns",
        "gentoo": "sudo emerge slirp4netns",
        "alpine": "sudo apk add slirp4netns",
        "void": "sudo xbps-install slirp4netns",
        "nixos": "nix-env -iA nixpkgs.slirp4netns",
    }

    if distro in instructions:
        return instructions[distro]

    # Fallback - check for package manager
    if shutil.which("apt"):
        return "sudo apt install slirp4netns"
    elif shutil.which("dnf"):
        return "sudo dnf install slirp4netns"
    elif shutil.which("pacman"):
        return "sudo pacman -S slirp4netns"
    elif shutil.which("zypper"):
        return "sudo zypper install slirp4netns"

    return "Install slirp4netns using your package manager"


def resolve_hostname(host: str) -> tuple[list[str], list[str]]:
    """Resolve hostname to IPv4 and IPv6 addresses.

    Args:
        host: Hostname to resolve (e.g., 'github.com')

    Returns:
        Tuple of (ipv4_list, ipv6_list) with deduplicated addresses.
    """
    ipv4: list[str] = []
    ipv6: list[str] = []

    try:
        # Get all address info (both IPv4 and IPv6)
        results = socket.getaddrinfo(host, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
        for family, _, _, _, sockaddr in results:
            ip = sockaddr[0]
            if family == socket.AF_INET:
                ipv4.append(ip)
            elif family == socket.AF_INET6:
                ipv6.append(ip)
    except socket.gaierror:
        pass  # Host resolution failed

    return (list(set(ipv4)), list(set(ipv6)))  # Dedupe


def get_www_variant(host: str) -> str | None:
    """Get the www variant of a hostname.

    Args:
        host: Hostname (e.g., 'github.com' or 'www.github.com')

    Returns:
        The www variant if host doesn't start with www.,
        the non-www variant if it does, or None if neither applies.
    """
    if host.startswith("www."):
        return host[4:]  # Strip www.
    elif "." in host and not host.startswith("www."):
        return f"www.{host}"  # Add www.
    return None


def is_ipv6(cidr: str) -> bool:
    """Check if CIDR is IPv6.

    Args:
        cidr: IP address or CIDR range string

    Returns:
        True if IPv6, False otherwise.
    """
    try:
        network = ipaddress.ip_network(cidr, strict=False)
        return network.version == 6
    except ValueError:
        return False


def validate_cidr(cidr: str) -> bool:
    """Validate if string is a valid CIDR or IP address.

    Args:
        cidr: IP address or CIDR range string

    Returns:
        True if valid, False otherwise.
    """
    try:
        ipaddress.ip_network(cidr, strict=False)
        return True
    except ValueError:
        return False


def validate_port(port: int | str) -> bool:
    """Validate if port number is valid.

    Args:
        port: Port number (int or string)

    Returns:
        True if valid port (1-65535), False otherwise.
    """
    try:
        port_int = int(port)
        return 1 <= port_int <= 65535
    except (ValueError, TypeError):
        return False


def generate_iptables_rules(nf: NetworkFilter) -> tuple[list[str], list[str]]:
    """Generate iptables and ip6tables commands from filter config.

    Args:
        nf: NetworkFilter configuration

    Returns:
        Tuple of (iptables_rules, ip6tables_rules) as command strings.
    """
    from model.network_filter import FilterMode

    v4_rules: list[str] = []
    v6_rules: list[str] = []

    # Always allow loopback
    v4_rules.append("iptables -A OUTPUT -o lo -j ACCEPT")
    v4_rules.append("iptables -A INPUT -i lo -j ACCEPT")
    v6_rules.append("ip6tables -A OUTPUT -o lo -j ACCEPT")
    v6_rules.append("ip6tables -A INPUT -i lo -j ACCEPT")

    # Collect all IPs to allow/block
    v4_allow: list[str] = []
    v6_allow: list[str] = []
    v4_block: list[str] = []
    v6_block: list[str] = []

    # Process hostname filter
    hf = nf.hostname_filter
    if hf.mode != FilterMode.OFF:
        for host in hf.hosts:
            ipv4s, ipv6s = resolve_hostname(host)
            if hf.mode == FilterMode.WHITELIST:
                v4_allow.extend(ipv4s)
                v6_allow.extend(ipv6s)
            else:  # BLACKLIST
                v4_block.extend(ipv4s)
                v6_block.extend(ipv6s)

    # Process IP filter
    ipf = nf.ip_filter
    if ipf.mode != FilterMode.OFF:
        for cidr in ipf.cidrs:
            if is_ipv6(cidr):
                if ipf.mode == FilterMode.WHITELIST:
                    v6_allow.append(cidr)
                else:
                    v6_block.append(cidr)
            else:
                if ipf.mode == FilterMode.WHITELIST:
                    v4_allow.append(cidr)
                else:
                    v4_block.append(cidr)

    # Generate rules - blacklist first (explicit blocks)
    for ip in v4_block:
        v4_rules.append(f"iptables -A OUTPUT -d {ip} -j DROP")
    for ip in v6_block:
        v6_rules.append(f"ip6tables -A OUTPUT -d {ip} -j DROP")

    # Then whitelist (explicit allows)
    for ip in v4_allow:
        v4_rules.append(f"iptables -A OUTPUT -d {ip} -j ACCEPT")
    for ip in v6_allow:
        v6_rules.append(f"ip6tables -A OUTPUT -d {ip} -j ACCEPT")

    # If any whitelist is active, drop everything else
    has_whitelist = hf.mode == FilterMode.WHITELIST or ipf.mode == FilterMode.WHITELIST
    if has_whitelist:
        v4_rules.append("iptables -A OUTPUT -j DROP")
        v6_rules.append("ip6tables -A OUTPUT -j DROP")

    return (v4_rules, v6_rules)


def generate_init_script(
    nf: NetworkFilter,
    iptables_path: str,
    ip6tables_path: str | None,
    is_multicall: bool,
) -> str:
    """Generate an init script that sets up iptables rules.

    This script is run inside the sandbox before the user command
    to set up network filtering rules.

    Args:
        nf: NetworkFilter configuration
        iptables_path: Resolved path to iptables binary
        ip6tables_path: Resolved path to ip6tables binary (may be None)
        is_multicall: True if the binary is a multi-call binary (like xtables-nft-multi)

    Returns:
        Shell script content as a string.
    """
    v4_rules, v6_rules = generate_iptables_rules(nf)

    lines = []

    # For multi-call binaries (xtables-nft-multi), invoke as: /path/to/binary iptables <args>
    # For regular binaries, invoke as: /path/to/iptables <args>
    if is_multicall:
        v4_cmd = f"{iptables_path} iptables"
        v6_cmd = f"{ip6tables_path} ip6tables" if ip6tables_path else None
    else:
        v4_cmd = iptables_path
        v6_cmd = ip6tables_path

    lines.append("# IPv4 rules")
    for rule in v4_rules:
        lines.append(rule.replace("iptables", v4_cmd))
    lines.append("")

    if v6_cmd and v6_rules:
        lines.append("# IPv6 rules")
        for rule in v6_rules:
            lines.append(rule.replace("ip6tables", v6_cmd))
        lines.append("")

    return "\n".join(lines)


def generate_slirp4netns_args(
    nf: NetworkFilter, pid: int, userns_path: str | None = None
) -> list[str]:
    """Generate slirp4netns command with port forwards.

    Args:
        nf: NetworkFilter configuration
        pid: Process ID of the sandbox to attach to
        userns_path: Path to user namespace (e.g., /proc/PID/ns/user)
                     Required when sandbox uses --unshare-user

    Returns:
        Command arguments for slirp4netns.
    """
    args = ["slirp4netns", "--configure", "--mtu=65520"]

    # If sandbox is in a user namespace, slirp4netns needs to join it first
    if userns_path:
        args.extend(["--userns-path", userns_path])

    # Add localhost port forwards
    has_port_forwards = len(nf.localhost_access.ports) > 0
    for port in nf.localhost_access.ports:
        args.extend(["-p", f"{port}:127.0.0.1:{port}"])

    # Disable host loopback access unless we have port forwards
    if not has_port_forwards:
        args.append("--disable-host-loopback")

    args.extend([str(pid), "tap0"])
    return args


def get_slirp4netns_status() -> tuple[bool, str]:
    """Get slirp4netns installation status and install command.

    Returns:
        Tuple of (is_installed, install_command_or_status_message).
    """
    if check_slirp4netns():
        return (True, "slirp4netns installed")
    else:
        return (False, get_install_instructions())


def execute_with_network_filter(
    config: "SandboxConfig",
    fd_map: dict[str, int] | None,
    build_command_fn: callable,
    sandbox_name: str | None = None,
    overlay_dirs: list[str] | None = None,
) -> None:
    """Execute bwrap with network filtering via slirp4netns.

    The key challenge: slirp4netns needs CAP_SYS_ADMIN to join the network
    namespace via setns(). Unprivileged users don't have this capability.

    Solution: Create a user namespace first (via unshare), which gives us
    capabilities inside that namespace. Then run bwrap and slirp4netns
    from within that user namespace.

    Args:
        config: SandboxConfig with network_filter enabled
        fd_map: Optional FD mapping for virtual user files
        build_command_fn: Function to build bwrap command from config
        sandbox_name: Optional sandbox name for overlay info
        overlay_dirs: Optional list of overlay directories
    """
    import os
    import shlex
    import sys
    import tempfile

    nf = config.network_filter

    # Fail fast: check iptables availability
    iptables_path, ip6tables_path, is_multicall = find_iptables()
    if iptables_path is None:
        print("=" * 60, file=sys.stderr)
        print("Error: iptables not found", file=sys.stderr)
        print("", file=sys.stderr)
        print("Network filtering requires iptables.", file=sys.stderr)
        print("Install with your package manager (e.g. iptables, nftables)", file=sys.stderr)
        print("=" * 60, file=sys.stderr)
        sys.exit(1)

    # Create temp directory for scripts
    tmp_dir = tempfile.mkdtemp(prefix="bui-net-")
    tmp_path = Path(tmp_dir)
    init_script_path = tmp_path / "init.sh"
    ready_file = tmp_path / "ready"

    # Generate iptables init script content
    iptables_script = generate_init_script(nf, iptables_path, ip6tables_path, is_multicall)

    # Build the user command as a shell-safe string
    user_cmd = " ".join(shlex.quote(arg) for arg in config.command)

    # Create the init wrapper script
    # NOTE: This script runs INSIDE the sandbox (in the network namespace)
    init_wrapper = f'''#!/bin/sh
# This script runs INSIDE the sandbox (in the network namespace)
set -e

# Wait for ready signal (parent creates this after slirp4netns attaches)
for i in $(seq 1 60); do
    if [ -f {ready_file} ]; then
        break
    fi
    sleep 0.5
done

if [ ! -f {ready_file} ]; then
    echo "Error: Timeout waiting for network setup signal" >&2
    exit 1
fi

# Wait for slirp4netns to set up networking (creates tap0)
for i in $(seq 1 20); do
    if ip link show tap0 >/dev/null 2>&1; then
        break
    fi
    sleep 0.5
done

if ! ip link show tap0 >/dev/null 2>&1; then
    echo "Error: Network setup failed (tap0 not found)" >&2
    exit 1
fi

# Configure loopback
ip link set lo up 2>/dev/null || true
ip addr add 127.0.0.1/8 dev lo 2>/dev/null || true

# tap0 is already configured by slirp4netns --configure
# (IP 10.0.2.100/24, gateway 10.0.2.2, DNS 10.0.2.3)

# Set up iptables rules
{iptables_script}

# Run the user command
exec {user_cmd}
'''

    init_script_path.write_text(init_wrapper)
    init_script_path.chmod(0o755)

    # Build bwrap command with network isolation
    original_command = config.command
    config.command = [str(init_script_path)]

    cmd = build_command_fn(config, fd_map)
    config.command = original_command

    # Find the "--" separator and insert bind mount BEFORE it
    try:
        separator_idx = cmd.index("--")
        cmd.insert(separator_idx, "--bind")
        cmd.insert(separator_idx + 1, tmp_dir)
        cmd.insert(separator_idx + 2, tmp_dir)
    except ValueError:
        cmd.extend(["--bind", tmp_dir, tmp_dir])

    # Remove CAP_NET_ADMIN from drop_caps if present, and add it explicitly
    try:
        cap_drop_idx = cmd.index("--cap-drop")
        while cap_drop_idx < len(cmd) - 1:
            if cmd[cap_drop_idx] == "--cap-drop" and cmd[cap_drop_idx + 1] == "CAP_NET_ADMIN":
                cmd.pop(cap_drop_idx)
                cmd.pop(cap_drop_idx)
                break
            cap_drop_idx = cmd.index("--cap-drop", cap_drop_idx + 1)
    except ValueError:
        pass

    # Add CAP_NET_ADMIN capability
    separator_idx = cmd.index("--")
    cmd.insert(separator_idx, "--cap-add")
    cmd.insert(separator_idx + 1, "CAP_NET_ADMIN")

    # Print header
    from commandoutput import print_execution_header
    print_execution_header(
        cmd,
        network_filter=nf,
        sandbox_name=sandbox_name,
        overlay_dirs=overlay_dirs,
    )

    # Create a wrapper script that:
    # 1. Runs inside a user namespace (via unshare)
    # 2. Starts bwrap with --unshare-net
    # 3. Starts slirp4netns to attach to bwrap's network namespace
    # 4. Signals the init script when ready
    #
    # We need the user namespace because slirp4netns needs CAP_SYS_ADMIN
    # to join the network namespace via setns().
    wrapper_script = tmp_path / "wrapper.sh"
    bwrap_cmd_str = " ".join(shlex.quote(arg) for arg in cmd)
    slirp_template = " ".join(shlex.quote(arg) for arg in generate_slirp4netns_args(nf, 0, userns_path=None))
    # Replace the placeholder PID with $SANDBOX_PID
    slirp_template = slirp_template.replace(" 0 ", " $SANDBOX_PID ")

    slirp_log = tmp_path / "slirp.log"
    wrapper_content = f'''#!/bin/sh
# This runs inside a user namespace (created by unshare --user --map-root-user)
# giving us CAP_SYS_ADMIN to join the network namespace
set -e

# Start bwrap in background
{bwrap_cmd_str} &
BWRAP_PID=$!

# Wait for bwrap to start
sleep 0.3

# Find the sandboxed process (child of bwrap)
SANDBOX_PID=""
for i in $(seq 1 50); do
    if [ -f /proc/$BWRAP_PID/task/$BWRAP_PID/children ]; then
        SANDBOX_PID=$(cat /proc/$BWRAP_PID/task/$BWRAP_PID/children | cut -d' ' -f1)
        if [ -n "$SANDBOX_PID" ]; then
            break
        fi
    fi
    sleep 0.1
done

if [ -z "$SANDBOX_PID" ]; then
    SANDBOX_PID=$BWRAP_PID
fi

# Start slirp4netns (suppress output unless error)
{slirp_template} >{slirp_log} 2>&1 &
SLIRP_PID=$!

# Wait for slirp4netns to start
sleep 0.3

# Check if slirp4netns is still running
if ! kill -0 $SLIRP_PID 2>/dev/null; then
    echo "Error: slirp4netns failed to start:" >&2
    cat {slirp_log} >&2
    kill $BWRAP_PID 2>/dev/null || true
    exit 1
fi

# Signal init script to continue
echo "ready" > {ready_file}

# Wait for bwrap to exit
wait $BWRAP_PID
EXIT_CODE=$?

# Clean up slirp4netns
kill $SLIRP_PID 2>/dev/null || true

exit $EXIT_CODE
'''

    wrapper_script.write_text(wrapper_content)
    wrapper_script.chmod(0o755)

    # Run the wrapper inside a user namespace using unshare
    # --user: create user namespace
    # --map-root-user: map current user to root in the namespace (gives capabilities)
    unshare_cmd = [
        "unshare",
        "--user",
        "--map-root-user",
        str(wrapper_script),
    ]

    # Execute unshare (replaces current process)
    os.execvp("unshare", unshare_cmd)
