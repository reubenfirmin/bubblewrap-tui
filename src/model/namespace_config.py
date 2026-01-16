"""Namespace isolation configuration model."""

from model.ui_field import ConfigBase, UIField


class NamespaceConfig(ConfigBase):
    """Namespace isolation settings for the sandbox."""

    unshare_user = UIField(
        bool, False, "opt-unshare-user",
        "User namespace", "Appear as different user inside",
        bwrap_flag="--unshare-user",
        summary="user namespace (appears as different user inside)",
    )
    unshare_pid = UIField(
        bool, False, "opt-unshare-pid",
        "PID namespace", "Hide host processes",
        bwrap_flag="--unshare-pid",
        summary="PID namespace (can't see host processes)",
    )
    unshare_ipc = UIField(
        bool, False, "opt-unshare-ipc",
        "IPC namespace", "Isolated shared memory",
        bwrap_flag="--unshare-ipc",
        summary="IPC namespace (isolated shared memory)",
    )
    unshare_uts = UIField(
        bool, False, "opt-unshare-uts",
        "UTS namespace", "Own hostname inside",
        bwrap_flag="--unshare-uts",
        summary="UTS namespace (own hostname)",
    )
    unshare_cgroup = UIField(
        bool, False, "opt-unshare-cgroup",
        "Cgroup namespace", "Isolated resource limits",
        bwrap_flag="--unshare-cgroup",
        summary="cgroup namespace (isolated resource limits)",
    )
    disable_userns = UIField(
        bool, False, "opt-disable-userns",
        "Disable nested sandboxing", "Prevent user namespaces inside",
        bwrap_flag="--disable-userns",
        summary="User namespaces: DISABLED (prevents nested sandboxing)",
    )
