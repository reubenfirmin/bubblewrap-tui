"""Optional seccomp support - requires libseccomp Python bindings.

Seccomp (secure computing mode) filters syscalls at the kernel level,
reducing kernel attack surface by blocking dangerous syscalls like:
- kexec_load - load new kernel
- io_uring_* - many CVEs (CVE-2022-29582, CVE-2023-2598, etc.)
- perf_event_open - kernel profiling exploits
- userfaultfd - exploit primitive for race conditions
"""

from __future__ import annotations

# Safe to block - no legitimate use inside a sandbox
BLOCKED_SYSCALLS_BASE = [
    # Kernel/system modification
    "kexec_load",
    "kexec_file_load",
    "reboot",
    "swapon",
    "swapoff",
    "acct",
    # Module loading
    "init_module",
    "finit_module",
    "delete_module",
]

# May break software - exploit primitives that have legitimate uses
BLOCKED_SYSCALLS_STRICT = [
    # Kernel profiling/monitoring (exploit primitives)
    # Breaks: profilers, some JIT compilers
    "perf_event_open",
    # Breaks: file monitoring tools, antivirus
    "fanotify_init",
    # Breaks: NFS servers, some backup tools
    "open_by_handle_at",
    # Breaks: QEMU, some garbage collectors
    "userfaultfd",
    # Breaks: PostgreSQL, Redis, nginx, Node.js, Rust tokio
    "io_uring_setup",
    "io_uring_enter",
    "io_uring_register",
]

# Combined list for backward compatibility
BLOCKED_SYSCALLS = BLOCKED_SYSCALLS_BASE + BLOCKED_SYSCALLS_STRICT


def _get_seccomp_module():
    """Get the seccomp module (either pyseccomp or seccomp)."""
    # Try pyseccomp first (pure Python, available on PyPI)
    try:
        import pyseccomp
        return pyseccomp
    except ImportError:
        pass
    # Fall back to system seccomp (C extension)
    try:
        import seccomp
        return seccomp
    except ImportError:
        pass
    return None


def check_seccomp() -> bool:
    """Check if libseccomp Python bindings are available."""
    mod = _get_seccomp_module()
    return mod is not None and hasattr(mod, "SyscallFilter")


def get_seccomp_status() -> tuple[bool, str]:
    """Return (available, install_hint).

    Returns:
        Tuple of (is_available, installation_hint_message)
    """
    if check_seccomp():
        return True, ""

    return False, _get_install_hint()


def _get_install_hint() -> str:
    """Get distro-specific install command for seccomp Python bindings."""
    import shutil

    from net.utils import detect_distro

    distro = detect_distro()

    instructions = {
        "fedora": "sudo dnf install python3-libseccomp",
        "rhel": "sudo dnf install python3-libseccomp",
        "centos": "sudo dnf install python3-libseccomp",
        "debian": "sudo apt install python3-libseccomp",
        "ubuntu": "sudo apt install python3-libseccomp",
        "arch": "sudo pacman -S python-seccomp",
        "manjaro": "sudo pacman -S python-seccomp",
        "opensuse": "sudo zypper install python3-seccomp",
        "opensuse-leap": "sudo zypper install python3-seccomp",
        "opensuse-tumbleweed": "sudo zypper install python3-seccomp",
        "alpine": "sudo apk add py3-libseccomp",
    }

    if distro in instructions:
        return instructions[distro]

    if shutil.which("apt"):
        return "sudo apt install python3-libseccomp"
    elif shutil.which("dnf"):
        return "sudo dnf install python3-libseccomp"
    elif shutil.which("pacman"):
        return "sudo pacman -S python-seccomp"

    return "pip install pyseccomp"


def generate_seccomp_filter(blocked: list[str] | None = None) -> bytes | None:
    """Generate BPF filter bytes for bwrap --seccomp.

    Args:
        blocked: List of syscall names to block. Defaults to BLOCKED_SYSCALLS.

    Returns:
        BPF filter bytes suitable for bwrap --seccomp FD, or None if
        libseccomp is unavailable.
    """
    import os
    import tempfile

    seccomp = _get_seccomp_module()
    if seccomp is None:
        return None

    if blocked is None:
        blocked = BLOCKED_SYSCALLS

    # Create filter that allows everything by default
    # SCMP_ACT_ALLOW = allow syscall
    f = seccomp.SyscallFilter(seccomp.ALLOW)

    # Block specific syscalls with EPERM
    for syscall_name in blocked:
        try:
            f.add_rule(seccomp.ERRNO(1), syscall_name)  # EPERM = 1
        except (OSError, ValueError):
            # OSError: syscall not found on this architecture
            # ValueError: invalid syscall name
            continue

    # Export as BPF program
    # pyseccomp requires a real file, not BytesIO
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            tmp_path = tmp.name
            f.export_bpf(tmp)

        with open(tmp_path, "rb") as fp:
            return fp.read()
    finally:
        if tmp_path is not None:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


def create_seccomp_filter_file(tmp_dir: str) -> str | None:
    """Create temp file with BPF filter, return path.

    Args:
        tmp_dir: Directory to create the filter file in.

    Returns:
        Path to the created BPF filter file, or None if libseccomp
        is unavailable.
    """
    from pathlib import Path

    bpf_data = generate_seccomp_filter()
    if bpf_data is None:
        return None

    filter_path = Path(tmp_dir) / "seccomp.bpf"
    filter_path.write_bytes(bpf_data)
    filter_path.chmod(0o444)  # Read-only

    return str(filter_path)
