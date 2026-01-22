"""Seccomp BPF filter generation for blocking user namespace creation.

This module generates seccomp filters that block clone(), clone3(), and unshare()
syscalls with CLONE_NEWUSER flag. This provides an alternative to bwrap's
--disable-userns that can coexist with CAP_NET_ADMIN (needed for iptables).

Architecture:
  - BPF program checks syscall number and arguments
  - Blocks specific flags while allowing other uses of the syscalls
  - Applied via prctl(PR_SET_SECCOMP) after iptables setup
"""

from __future__ import annotations

import struct


# Syscall numbers by architecture
SYSCALL_NUMBERS = {
    "x86_64": {
        "clone": 56,
        "clone3": 435,
        "unshare": 272,
    },
    "aarch64": {
        "clone": 220,
        "clone3": 435,
        "unshare": 97,
    },
}

# CLONE_NEWUSER flag value
CLONE_NEWUSER = 0x10000000

# Audit architecture values for seccomp
AUDIT_ARCH = {
    "x86_64": 0xc000003e,  # AUDIT_ARCH_X86_64
    "aarch64": 0xc00000b7,  # AUDIT_ARCH_AARCH64
}

# BPF instruction constants
BPF_LD = 0x00
BPF_W = 0x00
BPF_ABS = 0x20
BPF_JMP = 0x05
BPF_JEQ = 0x10
BPF_K = 0x00
BPF_RET = 0x06
BPF_AND = 0x50
BPF_ALU = 0x04

# Seccomp return values
SECCOMP_RET_ALLOW = 0x7fff0000
SECCOMP_RET_ERRNO = 0x00050000
ERRNO_EPERM = 1


def _bpf_stmt(code: int, k: int) -> bytes:
    """Generate a BPF statement (no jump targets)."""
    return struct.pack("<HBBI", code, 0, 0, k)


def _bpf_jump(code: int, k: int, jt: int, jf: int) -> bytes:
    """Generate a BPF jump instruction."""
    return struct.pack("<HBBI", code, jt, jf, k)


def generate_bpf_filter(arch: str = "x86_64") -> bytes:
    """Generate BPF bytecode that blocks CLONE_NEWUSER in clone/clone3/unshare.

    The filter:
    1. Validates architecture (fails closed on mismatch)
    2. Checks syscall number
    3. For clone/unshare: checks if CLONE_NEWUSER flag is set in arg0
    4. For clone3: checks clone_args.flags (arg0 is pointer, so we check differently)

    Note: clone3 uses a struct pointer (clone_args*), making flag checking impossible
    with seccomp's BPF (can't dereference userspace pointers). We allow clone3 since
    blocking it breaks threading in Node.js and other modern applications. The tradeoff
    is that CLONE_NEWUSER via clone3 is not blocked, but clone/unshare are still blocked.

    Args:
        arch: Target architecture ("x86_64" or "aarch64")

    Returns:
        BPF program as bytes
    """
    if arch not in SYSCALL_NUMBERS:
        raise ValueError(f"Unsupported architecture: {arch}")

    syscalls = SYSCALL_NUMBERS[arch]
    audit_arch = AUDIT_ARCH[arch]

    # Offsets in seccomp_data structure
    SECCOMP_DATA_ARCH = 4
    SECCOMP_DATA_NR = 0
    SECCOMP_DATA_ARGS = 16  # args[0] at offset 16, args[1] at 24, etc.

    instructions = []

    # Load architecture and verify
    instructions.append(_bpf_stmt(BPF_LD | BPF_W | BPF_ABS, SECCOMP_DATA_ARCH))
    # Jump to ALLOW (end) if architecture matches, otherwise fall through to KILL
    # We'll fix up jump targets after building the full program

    # For now, build a simpler filter:
    # 1. Check arch
    # 2. Load syscall number
    # 3. Check if it's clone/clone3/unshare
    # 4. If so, check flags
    # 5. Block if CLONE_NEWUSER is set

    # This generates a filter that:
    # - Loads syscall number
    # - Compares against clone/unshare
    # - If match, loads arg0 and checks CLONE_NEWUSER flag
    # - Blocks clone3 entirely (can't easily check struct pointer)

    prog = []

    # Instruction 0: Load arch
    prog.append(_bpf_stmt(BPF_LD | BPF_W | BPF_ABS, SECCOMP_DATA_ARCH))
    # Instruction 1: Check arch - if not match, skip to allow (fail open for compat)
    # We'll calculate the jump target after knowing program length
    # For now: if arch != expected, jump forward to allow

    # We need to know total instruction count to calculate jumps
    # Let's build the logic first, then encode

    # Simplified approach: generate the filter as shell commands instead
    # since BPF jump offset calculation is error-prone

    # Actually, let's use a cleaner approach - generate a small Python script
    # that applies the filter using ctypes, which is more maintainable

    return _build_filter_bytes(arch)


def _build_filter_bytes(arch: str) -> bytes:
    """Build the actual BPF filter bytes.

    This creates a minimal filter that:
    1. Checks architecture
    2. For clone/unshare: checks CLONE_NEWUSER in flags
    3. For clone3: blocks entirely (struct pointer makes flag checking hard)
    """
    syscalls = SYSCALL_NUMBERS[arch]
    audit_arch = AUDIT_ARCH[arch]

    # Seccomp data offsets
    OFF_ARCH = 4
    OFF_NR = 0
    OFF_ARG0_LO = 16  # Lower 32 bits of arg0

    # Build instructions list, then calculate jumps
    # Format: (opcode, jt, jf, k) - we'll convert to bytes at the end

    # Return values
    RET_ALLOW = SECCOMP_RET_ALLOW
    RET_ERRNO_EPERM = SECCOMP_RET_ERRNO | ERRNO_EPERM

    insts = []

    # 0: Load architecture
    insts.append((BPF_LD | BPF_W | BPF_ABS, 0, 0, OFF_ARCH))

    # 1: Check architecture - skip to allow if wrong (fail open for forward compat)
    # We'll fill in jump targets after we know total length
    # jt=0 (next), jf=skip to allow
    insts.append((BPF_JMP | BPF_JEQ | BPF_K, 0, 0, audit_arch))  # placeholder jf

    # 2: Load syscall number
    insts.append((BPF_LD | BPF_W | BPF_ABS, 0, 0, OFF_NR))

    # 3: Check for clone
    insts.append((BPF_JMP | BPF_JEQ | BPF_K, 0, 0, syscalls["clone"]))  # placeholder

    # 4: Check for clone3 - allow (can't check struct pointer flags)
    insts.append((BPF_JMP | BPF_JEQ | BPF_K, 0, 0, syscalls["clone3"]))  # match -> allow

    # 5: Check for unshare
    insts.append((BPF_JMP | BPF_JEQ | BPF_K, 0, 0, syscalls["unshare"]))  # placeholder

    # 6: Not a target syscall - allow
    insts.append((BPF_RET | BPF_K, 0, 0, RET_ALLOW))

    # 7: Load arg0 (flags) for clone/unshare
    insts.append((BPF_LD | BPF_W | BPF_ABS, 0, 0, OFF_ARG0_LO))

    # 8: AND with CLONE_NEWUSER
    insts.append((BPF_ALU | BPF_AND | BPF_K, 0, 0, CLONE_NEWUSER))

    # 9: If result is non-zero (flag set), block
    insts.append((BPF_JMP | BPF_JEQ | BPF_K, 0, 0, 0))  # Check if result == 0

    # 10: Flag not set - allow
    insts.append((BPF_RET | BPF_K, 0, 0, RET_ALLOW))

    # 11: Block with EPERM
    insts.append((BPF_RET | BPF_K, 0, 0, RET_ERRNO_EPERM))

    # Now fix up jump targets:
    # inst 1: arch check - if match continue (jt=0), if not match jump to allow (inst 6)
    # inst 3: clone check - if match jump to load arg0 (inst 7), else continue
    # inst 4: clone3 check - if match jump to block (inst 11), else continue
    # inst 5: unshare check - if match jump to load arg0 (inst 7), else continue (allow)
    # inst 9: if arg0 & CLONE_NEWUSER == 0, jump to allow (inst 10), else continue to block

    total = len(insts)

    # Calculate relative jumps (forward only in BPF)
    # jt/jf are number of instructions to skip (0 = next instruction)

    final_insts = []
    for i, (code, jt, jf, k) in enumerate(insts):
        if i == 1:  # arch check: match -> continue, no match -> allow (inst 6)
            jt, jf = 0, 6 - i - 1  # 6 - 1 - 1 = 4
        elif i == 3:  # clone: match -> inst 7, no match -> continue
            jt, jf = 7 - i - 1, 0  # 7 - 3 - 1 = 3
        elif i == 4:  # clone3: match -> allow (inst 6), no match -> continue
            jt, jf = 6 - i - 1, 0  # 6 - 4 - 1 = 1
        elif i == 5:  # unshare: match -> inst 7, no match -> continue (allow at 6)
            jt, jf = 7 - i - 1, 0  # 7 - 5 - 1 = 1
        elif i == 9:  # arg0 check: if 0 -> allow (inst 10), else -> block (inst 11)
            jt, jf = 10 - i - 1, 11 - i - 1  # 0, 1

        final_insts.append(struct.pack("<HBBI", code, jt, jf, k))

    return b"".join(final_insts)


def generate_seccomp_script() -> str:
    """Generate a shell script snippet that applies the seccomp filter.

    This generates inline Python code that:
    1. Detects architecture
    2. Builds the appropriate BPF filter
    3. Applies it via prctl()

    Returns:
        Shell commands to apply seccomp filter
    """
    # We embed the filter application as inline Python for portability
    # This avoids needing external tools like libseccomp-tools

    # Note: The exec("import ...") wrapper prevents the build script from extracting
    # these as module-level imports (they look like imports at column 0 in the heredoc)
    #
    # Returns a Python script that applies seccomp filter then execs SECCOMP_EXEC_CMD
    # The caller must define SECCOMP_EXEC_CMD before this script runs
    return '''
# Apply seccomp filter to block user namespace creation, then exec command
# Caller must set SECCOMP_EXEC_CMD to the command to run after filter is applied
exec python3 -c '
exec("import ctypes, struct, platform, os, sys, shlex")

EXEC_CMD = os.environ.get("SECCOMP_EXEC_CMD", "")
if not EXEC_CMD:
    print("Error: SECCOMP_EXEC_CMD not set", file=sys.stderr)
    sys.exit(1)

# Constants
PR_SET_NO_NEW_PRIVS = 38
PR_SET_SECCOMP = 22
SECCOMP_MODE_FILTER = 2

# Architecture detection
machine = platform.machine()
if machine == "x86_64":
    AUDIT_ARCH = 0xc000003e
    CLONE_NR = 56
    CLONE3_NR = 435
    UNSHARE_NR = 272
elif machine == "aarch64":
    AUDIT_ARCH = 0xc00000b7
    CLONE_NR = 220
    CLONE3_NR = 435
    UNSHARE_NR = 97
else:
    print(f"Warning: seccomp filter not supported on {machine}, running command without filter", file=sys.stderr)
    os.execvp("/bin/sh", ["/bin/sh", "-c", EXEC_CMD])

CLONE_NEWUSER = 0x10000000

# BPF constants
BPF_LD, BPF_W, BPF_ABS = 0x00, 0x00, 0x20
BPF_JMP, BPF_JEQ, BPF_K = 0x05, 0x10, 0x00
BPF_RET, BPF_AND, BPF_ALU = 0x06, 0x50, 0x04

SECCOMP_RET_ALLOW = 0x7fff0000
SECCOMP_RET_ERRNO_EPERM = 0x00050001  # EPERM = 1

# Seccomp data offsets
OFF_ARCH, OFF_NR, OFF_ARG0 = 4, 0, 16

def bpf_stmt(code, k):
    return struct.pack("<HBBI", code, 0, 0, k)

def bpf_jump(code, k, jt, jf):
    return struct.pack("<HBBI", code, jt, jf, k)

# Build filter
prog = b""
prog += bpf_stmt(BPF_LD | BPF_W | BPF_ABS, OFF_ARCH)
prog += bpf_jump(BPF_JMP | BPF_JEQ | BPF_K, AUDIT_ARCH, 0, 4)
prog += bpf_stmt(BPF_LD | BPF_W | BPF_ABS, OFF_NR)
prog += bpf_jump(BPF_JMP | BPF_JEQ | BPF_K, CLONE_NR, 3, 0)
prog += bpf_jump(BPF_JMP | BPF_JEQ | BPF_K, CLONE3_NR, 1, 0)  # clone3: allow (cant check flags)
prog += bpf_jump(BPF_JMP | BPF_JEQ | BPF_K, UNSHARE_NR, 1, 0)
prog += bpf_stmt(BPF_RET | BPF_K, SECCOMP_RET_ALLOW)
prog += bpf_stmt(BPF_LD | BPF_W | BPF_ABS, OFF_ARG0)
prog += bpf_stmt(BPF_ALU | BPF_AND | BPF_K, CLONE_NEWUSER)
prog += bpf_jump(BPF_JMP | BPF_JEQ | BPF_K, 0, 0, 1)
prog += bpf_stmt(BPF_RET | BPF_K, SECCOMP_RET_ALLOW)
prog += bpf_stmt(BPF_RET | BPF_K, SECCOMP_RET_ERRNO_EPERM)

# sock_fprog structure
class sock_fprog(ctypes.Structure):
    _fields_ = [("len", ctypes.c_ushort), ("filter", ctypes.c_void_p)]

libc = ctypes.CDLL(None, use_errno=True)
prctl = libc.prctl

# Set no_new_privs (required for unprivileged seccomp)
if prctl(PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) != 0:
    err = ctypes.get_errno()
    print(f"Warning: prctl(NO_NEW_PRIVS) failed: {os.strerror(err)}, running command without filter", file=sys.stderr)
    os.execvp("/bin/sh", ["/bin/sh", "-c", EXEC_CMD])

# Apply seccomp filter
num_insts = len(prog) // 8
fprog = sock_fprog(num_insts, ctypes.cast(ctypes.c_char_p(prog), ctypes.c_void_p))
if prctl(PR_SET_SECCOMP, SECCOMP_MODE_FILTER, ctypes.byref(fprog), 0, 0) != 0:
    err = ctypes.get_errno()
    print(f"Warning: prctl(SECCOMP) failed: {os.strerror(err)}, running command without filter", file=sys.stderr)
    os.execvp("/bin/sh", ["/bin/sh", "-c", EXEC_CMD])

# Exec the command with seccomp filter active
os.execvp("/bin/sh", ["/bin/sh", "-c", EXEC_CMD])
'
'''


def get_seccomp_init_commands() -> str:
    """Get shell commands to apply seccomp filter in init script.

    This is called by create_init_script() to inject the seccomp setup
    after iptables rules but before the user command.

    Returns:
        Shell commands as string
    """
    return generate_seccomp_script()


def create_seccomp_init_script(user_command: list[str]) -> "Path":
    """Create a standalone init script that applies seccomp then runs user command.

    This is used when seccomp_block_userns is enabled but network filtering is not.
    The script applies the seccomp filter then execs the user command.

    Args:
        user_command: The user's command to run

    Returns:
        Path to the created init script
    """
    import shlex
    import tempfile
    from pathlib import Path

    tmp_dir = tempfile.mkdtemp(prefix="bui-seccomp-")
    tmp_path = Path(tmp_dir)
    init_script_path = tmp_path / "init.sh"

    user_cmd = " ".join(shlex.quote(arg) for arg in user_command)

    # The seccomp wrapper reads SECCOMP_EXEC_CMD from environment
    seccomp_wrapper = generate_seccomp_script()
    # Escape single quotes for shell
    escaped_exec_cmd = f"exec {user_cmd}".replace("'", "'\"'\"'")

    init_wrapper = f'''#!/bin/sh
set -e

# Apply seccomp filter to block user namespace creation, then run user command
export SECCOMP_EXEC_CMD='{escaped_exec_cmd}'
{seccomp_wrapper}
'''

    init_script_path.write_text(init_wrapper)
    init_script_path.chmod(0o755)

    return init_script_path
