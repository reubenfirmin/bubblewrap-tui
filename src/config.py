"""Configuration dataclasses for bui."""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import ClassVar

from detection import (
    detect_dbus_session,
    detect_display_server,
    find_dns_paths,
    find_ssl_cert_paths,
)


@dataclass
class BoundDirectory:
    """A directory bound into the sandbox."""
    path: Path
    readonly: bool = True

    def __str__(self) -> str:
        mode = "ro" if self.readonly else "rw"
        return f"{self.path} ({mode})"

    def to_args(self) -> list[str]:
        """Convert to bwrap arguments."""
        flag = "--ro-bind" if self.readonly else "--bind"
        path_str = str(self.path)
        return [flag, path_str, path_str]


@dataclass
class OverlayConfig:
    """An overlay filesystem configuration."""
    source: str  # Real directory to overlay
    dest: str  # Mount point in sandbox
    mode: str = "tmpfs"  # "tmpfs" or "persistent"
    write_dir: str = ""  # For persistent mode - where changes are stored

    def get_work_dir(self) -> str:
        """Auto-generate work dir from write dir."""
        if self.write_dir:
            return str(Path(self.write_dir).parent / ".overlay-work")
        return ""

    def to_args(self) -> list[str]:
        """Convert to bwrap arguments."""
        if not self.source or not self.dest:
            return []
        args = ["--overlay-src", self.source]
        if self.mode == "tmpfs":
            args.extend(["--tmp-overlay", self.dest])
        elif self.mode == "persistent" and self.write_dir:
            work_dir = self.get_work_dir()
            args.extend(["--overlay", self.write_dir, work_dir, self.dest])
        return args


@dataclass
class SandboxConfig:
    """Configuration for the sandbox."""
    command: list[str] = field(default_factory=list)
    bound_dirs: list[BoundDirectory] = field(default_factory=list)

    # Special filesystems
    dev_mode: str = "minimal"  # "none", "minimal", "full"
    mount_proc: bool = True
    mount_tmp: bool = True

    # Network
    share_net: bool = False
    bind_resolv_conf: bool = False
    bind_ssl_certs: bool = False

    # Desktop integration
    allow_dbus: bool = False
    allow_display: bool = False
    bind_user_config: bool = False  # ~/.config for default apps, themes, etc.

    # Environment
    clear_env: bool = False
    keep_env_vars: set[str] = field(default_factory=set)
    unset_env_vars: set[str] = field(default_factory=set)
    custom_env_vars: dict[str, str] = field(default_factory=dict)

    # Hostname
    custom_hostname: str = ""

    # Namespaces
    unshare_user: bool = False
    unshare_pid: bool = False
    unshare_ipc: bool = False
    unshare_uts: bool = False
    unshare_cgroup: bool = False

    # Process
    die_with_parent: bool = True
    new_session: bool = True
    as_pid_1: bool = False
    chdir: str = ""

    # User/group mapping (used when unshare_user is True)
    uid: int = field(default_factory=os.getuid)
    gid: int = field(default_factory=os.getgid)

    # Advanced
    disable_userns: bool = False
    tmpfs_size: str = ""  # e.g., "100M", "1G"

    # Overlays
    overlays: list[OverlayConfig] = field(default_factory=list)

    # Capabilities (to drop)
    drop_caps: set[str] = field(default_factory=set)

    # System binds (read-only)
    bind_usr: bool = True
    bind_bin: bool = True
    bind_lib: bool = True
    bind_lib64: bool = True
    bind_sbin: bool = True
    bind_etc: bool = False

    SYSTEM_PATHS: ClassVar[dict[str, str]] = {
        "bind_usr": "/usr",
        "bind_bin": "/bin",
        "bind_lib": "/lib",
        "bind_lib64": "/lib64",
        "bind_sbin": "/sbin",
        "bind_etc": "/etc",
    }

    # Common capabilities that can be dropped, with descriptions
    ALL_CAPS: ClassVar[dict[str, str]] = {
        "CAP_CHOWN": "change file ownership",
        "CAP_DAC_OVERRIDE": "bypass file read/write/execute permission checks",
        "CAP_DAC_READ_SEARCH": "bypass file read permission and directory search",
        "CAP_FOWNER": "bypass permission checks requiring file owner match",
        "CAP_FSETID": "keep set-user-ID/set-group-ID bits when modifying files",
        "CAP_KILL": "send signals to processes owned by other users",
        "CAP_SETGID": "change process group ID",
        "CAP_SETUID": "change process user ID",
        "CAP_SETPCAP": "modify process capabilities",
        "CAP_LINUX_IMMUTABLE": "set immutable file attributes",
        "CAP_NET_BIND_SERVICE": "bind to privileged ports (below 1024)",
        "CAP_NET_BROADCAST": "send broadcast/multicast packets",
        "CAP_NET_ADMIN": "configure network interfaces and routing",
        "CAP_NET_RAW": "use raw network sockets (e.g., ping)",
        "CAP_IPC_LOCK": "lock memory pages",
        "CAP_IPC_OWNER": "bypass IPC permission checks",
        "CAP_SYS_MODULE": "load/unload kernel modules",
        "CAP_SYS_RAWIO": "access raw I/O ports",
        "CAP_SYS_CHROOT": "use chroot()",
        "CAP_SYS_PTRACE": "trace/debug other processes",
        "CAP_SYS_PACCT": "configure process accounting",
        "CAP_SYS_ADMIN": "perform privileged system operations (mount, namespace, etc.)",
        "CAP_SYS_BOOT": "reboot the system",
        "CAP_SYS_NICE": "raise process priority or change other processes' priority",
        "CAP_SYS_RESOURCE": "override resource limits",
        "CAP_SYS_TIME": "change the system clock",
        "CAP_SYS_TTY_CONFIG": "configure TTY devices",
        "CAP_MKNOD": "create device special files",
        "CAP_LEASE": "create file leases",
        "CAP_AUDIT_WRITE": "write to the kernel audit log",
        "CAP_AUDIT_CONTROL": "configure the audit subsystem",
        "CAP_SETFCAP": "set file capabilities",
    }

    def build_command(self) -> list[str]:
        """Build the complete bwrap command."""
        args = ["bwrap"]

        # System binds (read-only)
        for attr, path in self.SYSTEM_PATHS.items():
            if getattr(self, attr) and Path(path).exists():
                args.extend(["--ro-bind", path, path])

        # Special filesystems
        if self.dev_mode == "minimal":
            args.extend(["--dev", "/dev"])
        elif self.dev_mode == "full":
            args.extend(["--bind", "/dev", "/dev"])
        if self.mount_proc:
            args.extend(["--proc", "/proc"])
        if self.mount_tmp:
            if self.tmpfs_size:
                args.extend(["--size", self.tmpfs_size, "--tmpfs", "/tmp"])
            else:
                args.extend(["--tmpfs", "/tmp"])

        # Network
        if self.share_net:
            args.append("--share-net")
        if self.bind_resolv_conf:
            for dns_path in find_dns_paths():
                args.extend(["--ro-bind", dns_path, dns_path])
        if self.bind_ssl_certs:
            for cert_path in find_ssl_cert_paths():
                args.extend(["--ro-bind", cert_path, cert_path])

        # Desktop integration
        if self.allow_dbus:
            for dbus_path in detect_dbus_session():
                args.extend(["--bind", dbus_path, dbus_path])
        if self.allow_display:
            display_info = detect_display_server()
            for display_path in display_info["paths"]:
                args.extend(["--ro-bind", display_path, display_path])
        if self.bind_user_config:
            config_dir = Path.home() / ".config"
            if config_dir.exists():
                args.extend(["--ro-bind", str(config_dir), str(config_dir)])

        # Environment
        if self.clear_env:
            args.append("--clearenv")
            # Re-set kept vars
            for var in self.keep_env_vars:
                if var in os.environ:
                    args.extend(["--setenv", var, os.environ[var]])
        else:
            # Unset specific vars
            for var in self.unset_env_vars:
                args.extend(["--unsetenv", var])
        # Custom env vars
        for name, value in self.custom_env_vars.items():
            args.extend(["--setenv", name, value])

        # Hostname
        if self.custom_hostname:
            args.extend(["--hostname", self.custom_hostname])

        # Namespaces
        if self.unshare_user:
            args.append("--unshare-user")
        if self.unshare_pid:
            args.append("--unshare-pid")
        if self.unshare_ipc:
            args.append("--unshare-ipc")
        if self.unshare_uts:
            args.append("--unshare-uts")
        if self.unshare_cgroup:
            args.append("--unshare-cgroup")

        # Process options
        if self.die_with_parent:
            args.append("--die-with-parent")
        if self.new_session:
            args.append("--new-session")
        if self.as_pid_1:
            # --as-pid-1 requires --unshare-pid
            if not self.unshare_pid:
                args.append("--unshare-pid")
            args.append("--as-pid-1")
        if self.chdir:
            args.extend(["--chdir", self.chdir])

        # User/group mapping (when using user namespace)
        if self.unshare_user:
            args.extend(["--uid", str(self.uid)])
            args.extend(["--gid", str(self.gid)])

        # Advanced options
        if self.disable_userns:
            args.append("--disable-userns")

        # Overlay filesystems
        for overlay in self.overlays:
            args.extend(overlay.to_args())

        # Capabilities
        for cap in self.drop_caps:
            args.extend(["--cap-drop", cap])

        # User-bound directories
        for bound_dir in self.bound_dirs:
            args.extend(bound_dir.to_args())

        # Command separator and command
        args.append("--")
        args.extend(self.command)

        return args

    def get_explanation(self) -> str:
        """Generate a human-readable explanation of the sandbox."""
        lines = []

        # Command
        lines.append(f"• Running: {' '.join(self.command)}")

        # Network
        if self.share_net:
            extras = []
            if self.bind_resolv_conf:
                extras.append("DNS")
            if self.bind_ssl_certs:
                extras.append("SSL certs")
            if extras:
                lines.append(f"• Network: ALLOWED ({', '.join(extras)} included)")
            else:
                lines.append("• Network: ALLOWED (no DNS/SSL - may not work)")
        else:
            lines.append("• Network: BLOCKED (no network access)")

        # Desktop integration
        desktop = []
        if self.allow_dbus:
            desktop.append("D-Bus")
        if self.allow_display:
            display_info = detect_display_server()
            if display_info["type"]:
                desktop.append(display_info["type"].upper())
        if self.bind_user_config:
            desktop.append("~/.config")
        if desktop:
            lines.append(f"• Desktop: {', '.join(desktop)}")

        # Filesystem - system paths
        bound_sys = []
        for attr, path in self.SYSTEM_PATHS.items():
            if getattr(self, attr):
                bound_sys.append(path)
        if bound_sys:
            lines.append(f"• System paths (read-only): {', '.join(bound_sys)}")

        # Filesystem - user dirs
        if self.bound_dirs:
            ro_dirs = [str(d.path) for d in self.bound_dirs if d.readonly]
            rw_dirs = [str(d.path) for d in self.bound_dirs if not d.readonly]
            if ro_dirs:
                lines.append(f"• User directories (read-only): {', '.join(ro_dirs)}")
            if rw_dirs:
                lines.append(f"• User directories (read-write): {', '.join(rw_dirs)}")

        # Virtual filesystems
        vfs = []
        if self.dev_mode == "minimal":
            vfs.append("/dev (minimal)")
        elif self.dev_mode == "full":
            vfs.append("/dev (full host access)")
        if self.mount_proc:
            vfs.append("/proc")
        if self.mount_tmp:
            tmp_desc = "/tmp (ephemeral"
            if self.tmpfs_size:
                tmp_desc += f", max {self.tmpfs_size}"
            tmp_desc += ")"
            vfs.append(tmp_desc)
        if vfs:
            lines.append(f"• Virtual filesystems: {', '.join(vfs)}")

        # Overlays
        if self.overlays:
            lines.append(f"• Overlays ({len(self.overlays)}):")
            for ov in self.overlays:
                if ov.mode == "tmpfs":
                    lines.append(f"    - {ov.source} → {ov.dest} (tmpfs, discarded on exit)")
                else:
                    lines.append(f"    - {ov.source} → {ov.dest} (persistent to {ov.write_dir})")

        # Environment
        if self.clear_env:
            lines.append(f"• Environment: CLEARED, keeping {len(self.keep_env_vars)} vars")
        elif self.unset_env_vars:
            lines.append(f"• Environment: inherited minus {len(self.unset_env_vars)} removed vars")
        else:
            lines.append("• Environment: fully inherited from parent")

        if self.custom_env_vars:
            lines.append(f"• Custom env vars: {', '.join(self.custom_env_vars.keys())}")

        # Isolation
        isolation = []
        if self.unshare_user:
            isolation.append("user namespace (appears as different user inside)")
        if self.unshare_pid or self.as_pid_1:
            note = " (required by as-pid-1)" if self.as_pid_1 and not self.unshare_pid else ""
            isolation.append(f"PID namespace (can't see host processes){note}")
        if self.unshare_ipc:
            isolation.append("IPC namespace (isolated shared memory)")
        if self.unshare_uts:
            isolation.append("UTS namespace (own hostname)")
        if self.unshare_cgroup:
            isolation.append("cgroup namespace (isolated resource limits)")
        if isolation:
            lines.append("• Isolation namespaces:")
            for ns in isolation:
                lines.append(f"    - {ns}")

        # Capabilities
        if self.drop_caps:
            lines.append("• Sandbox CANNOT:")
            for cap in sorted(self.drop_caps):
                desc = self.ALL_CAPS.get(cap, "unknown")
                lines.append(f"    ✗ {desc.capitalize()}")

        # Process behavior
        process = []
        if self.die_with_parent:
            process.append("dies with parent")
        if self.new_session:
            process.append("new session")
        if self.as_pid_1:
            process.append("runs as PID 1 (init)")
        if self.chdir:
            process.append(f"workdir: {self.chdir}")
        if self.custom_hostname:
            process.append(f"hostname: {self.custom_hostname}")
        if process:
            lines.append(f"• Process: {', '.join(process)}")

        # User/group mapping
        if self.unshare_user:
            lines.append(f"• User mapping: UID {self.uid}, GID {self.gid}")

        # Advanced
        if self.disable_userns:
            lines.append("• User namespaces: DISABLED (prevents nested sandboxing)")

        return "\n".join(lines)
