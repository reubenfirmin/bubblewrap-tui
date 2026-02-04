"""Optional seccomp support - requires libseccomp Python bindings.

Seccomp (secure computing mode) filters syscalls at the kernel level,
reducing kernel attack surface by blocking dangerous syscalls like:
- kexec_load - load new kernel
- io_uring_* - many CVEs (CVE-2022-29582, CVE-2023-2598, etc.)
- perf_event_open - kernel profiling exploits
- userfaultfd - exploit primitive for race conditions
"""

from __future__ import annotations

# Syscalls to block - these provide minimal legitimate use but significant attack surface
BLOCKED_SYSCALLS = [
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
    # Kernel profiling/monitoring (exploit primitives)
    "perf_event_open",
    "fanotify_init",
    "open_by_handle_at",
    # Known CVE magnets
    "userfaultfd",
    "io_uring_setup",
    "io_uring_enter",
    "io_uring_register",
]


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
    """Get install command for seccomp Python bindings."""
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
        except Exception:
            # Syscall might not exist on this architecture, skip it
            pass

    # Export as BPF program
    # pyseccomp requires a real file, not BytesIO
    with tempfile.NamedTemporaryFile(delete=False) as tmp:
        f.export_bpf(tmp)
        tmp_path = tmp.name

    try:
        with open(tmp_path, "rb") as fp:
            return fp.read()
    finally:
        os.unlink(tmp_path)


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
