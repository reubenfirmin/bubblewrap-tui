"""UIField definitions for Isolation (Namespaces) group."""

from model.ui_field import UIField


def _named(name: str, field: UIField) -> UIField:
    """Set the name attribute on a UIField and return it."""
    field.name = name
    return field


unshare_pid = _named("unshare_pid", UIField(
    bool, True, "opt-unshare-pid",
    "Host processes",
    "Cannot see or signal host processes.",
    bwrap_flag="--unshare-pid",
    summary="Cannot see or signal host processes",
))

unshare_ipc = _named("unshare_ipc", UIField(
    bool, True, "opt-unshare-ipc",
    "Shared memory",
    "Gets own shared memory and semaphores, isolated from host.",
    bwrap_flag="--unshare-ipc",
    summary="Cannot access host shared memory or semaphores",
))

unshare_uts = _named("unshare_uts", UIField(
    bool, True, "opt-unshare-uts",
    "Isolate hostname",
    "Gets own hostname, cannot see or change host's.",
    bwrap_flag="--unshare-uts",
    summary="Isolated hostname — cannot see or modify host's hostname",
))

unshare_cgroup = _named("unshare_cgroup", UIField(
    bool, True, "opt-unshare-cgroup",
    "Cgroups",
    "Sees only its own resource accounting, not host's.",
    bwrap_flag="--unshare-cgroup",
    summary="Isolated cgroup view — sees only its own resource accounting",
))

disable_userns = _named("disable_userns", UIField(
    bool, False, "opt-disable-userns",
    "Nested sandboxing",
    "Cannot create containers inside (Docker, Podman, Flatpak). Breaks apps with internal sandboxing (Chrome, Electron).",
    bwrap_flag="--disable-userns",
    summary="Cannot create nested containers — prevents namespace escape attacks",
))

seccomp_block_userns = _named("seccomp_block_userns", UIField(
    bool, False, "opt-seccomp-block-userns",
    "Block nested sandboxing (seccomp)",
    "Block user namespace creation via seccomp filter. Alternative to bwrap's native option, works with network filtering.",
    summary="Seccomp blocks nested containers",
))
