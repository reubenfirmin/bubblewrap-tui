"""Bubblewrap command serialization and summarization.

These classes work with config objects only - no UI dependencies.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

from detection import (
    detect_dbus_session,
    detect_display_server,
    find_dns_paths,
    find_ssl_cert_paths,
)
from model.namespace_config import NamespaceConfig

if TYPE_CHECKING:
    from model.sandbox_config import SandboxConfig


class BubblewrapSerializer:
    """Serializes SandboxConfig to bwrap command-line arguments."""

    def __init__(self, config: SandboxConfig) -> None:
        self.config = config

    def serialize(self) -> list[str]:
        """Build the complete bwrap command."""
        args = ["bwrap"]

        self._add_filesystem_args(args)
        self._add_network_args(args)
        self._add_desktop_args(args)
        self._add_environment_args(args)
        self._add_namespace_args(args)
        self._add_process_args(args)
        self._add_overlay_args(args)
        self._add_capability_args(args)
        self._add_bound_dir_args(args)

        # Command separator and command
        args.append("--")
        args.extend(self.config.command)

        return args

    def _add_filesystem_args(self, args: list[str]) -> None:
        """Add filesystem-related arguments."""
        fs = self.config.filesystem

        # System binds (read-only)
        for attr, path in fs.SYSTEM_PATHS.items():
            if getattr(fs, attr) and Path(path).exists():
                args.extend(["--ro-bind", path, path])

        # Special filesystems
        if fs.dev_mode == "minimal":
            args.extend(["--dev", "/dev"])
        elif fs.dev_mode == "full":
            args.extend(["--bind", "/dev", "/dev"])

        if fs.mount_proc:
            args.extend(["--proc", "/proc"])

        if fs.mount_tmp:
            if fs.tmpfs_size:
                args.extend(["--size", fs.tmpfs_size, "--tmpfs", "/tmp"])
            else:
                args.extend(["--tmpfs", "/tmp"])

    def _add_network_args(self, args: list[str]) -> None:
        """Add network-related arguments."""
        net = self.config.network

        if net.share_net:
            args.append("--share-net")

        if net.bind_resolv_conf:
            for dns_path in find_dns_paths():
                args.extend(["--ro-bind", dns_path, dns_path])

        if net.bind_ssl_certs:
            for cert_path in find_ssl_cert_paths():
                args.extend(["--ro-bind", cert_path, cert_path])

    def _add_desktop_args(self, args: list[str]) -> None:
        """Add desktop integration arguments."""
        desktop = self.config.desktop

        if desktop.allow_dbus:
            for dbus_path in detect_dbus_session():
                args.extend(["--bind", dbus_path, dbus_path])

        if desktop.allow_display:
            display_info = detect_display_server()
            for display_path in display_info["paths"]:
                args.extend(["--ro-bind", display_path, display_path])

        if desktop.bind_user_config:
            config_dir = Path.home() / ".config"
            if config_dir.exists():
                args.extend(["--ro-bind", str(config_dir), str(config_dir)])

    def _add_environment_args(self, args: list[str]) -> None:
        """Add environment variable arguments."""
        env = self.config.environment

        if env.clear_env:
            args.append("--clearenv")
            # Re-set kept vars
            for var in env.keep_env_vars:
                if var in os.environ:
                    args.extend(["--setenv", var, os.environ[var]])
        else:
            # Unset specific vars
            for var in env.unset_env_vars:
                args.extend(["--unsetenv", var])

        # Custom env vars
        for name, value in env.custom_env_vars.items():
            args.extend(["--setenv", name, value])

        # Hostname
        if env.custom_hostname:
            args.extend(["--hostname", env.custom_hostname])

    def _add_namespace_args(self, args: list[str]) -> None:
        """Add namespace isolation arguments."""
        args.extend(self.config.namespace.to_bwrap_args())

    def _add_process_args(self, args: list[str]) -> None:
        """Add process control arguments."""
        proc = self.config.process
        ns = self.config.namespace

        if proc.die_with_parent:
            args.append("--die-with-parent")

        if proc.new_session:
            args.append("--new-session")

        if proc.as_pid_1:
            # --as-pid-1 requires --unshare-pid
            if not ns.unshare_pid:
                args.append("--unshare-pid")
            args.append("--as-pid-1")

        if proc.chdir:
            args.extend(["--chdir", proc.chdir])

        # User/group mapping (when using user namespace)
        if ns.unshare_user:
            args.extend(["--uid", str(proc.uid)])
            args.extend(["--gid", str(proc.gid)])

    def _add_overlay_args(self, args: list[str]) -> None:
        """Add overlay filesystem arguments."""
        for overlay in self.config.overlays:
            args.extend(overlay.to_args())

    def _add_capability_args(self, args: list[str]) -> None:
        """Add capability drop arguments."""
        for cap in self.config.drop_caps:
            args.extend(["--cap-drop", cap])

    def _add_bound_dir_args(self, args: list[str]) -> None:
        """Add user-bound directory arguments."""
        for bound_dir in self.config.bound_dirs:
            args.extend(bound_dir.to_args())


class BubblewrapSummarizer:
    """Generates human-readable summaries of SandboxConfig."""

    # Common capabilities that can be dropped, with descriptions
    ALL_CAPS: dict[str, str] = {
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

    def __init__(self, config: SandboxConfig) -> None:
        self.config = config

    def summarize(self) -> str:
        """Generate a human-readable explanation of the sandbox."""
        lines = []

        self._add_command_summary(lines)
        self._add_network_summary(lines)
        self._add_desktop_summary(lines)
        self._add_filesystem_summary(lines)
        self._add_overlay_summary(lines)
        self._add_environment_summary(lines)
        self._add_namespace_summary(lines)
        self._add_capability_summary(lines)
        self._add_process_summary(lines)

        return "\n".join(lines)

    def _add_command_summary(self, lines: list[str]) -> None:
        """Add command summary."""
        lines.append(f"• Running: {' '.join(self.config.command)}")

    def _add_network_summary(self, lines: list[str]) -> None:
        """Add network summary."""
        net = self.config.network

        if net.share_net:
            extras = []
            if net.bind_resolv_conf:
                extras.append("DNS")
            if net.bind_ssl_certs:
                extras.append("SSL certs")
            if extras:
                lines.append(f"• Network: ALLOWED ({', '.join(extras)} included)")
            else:
                lines.append("• Network: ALLOWED (no DNS/SSL - may not work)")
        else:
            lines.append("• Network: BLOCKED (no network access)")

    def _add_desktop_summary(self, lines: list[str]) -> None:
        """Add desktop integration summary."""
        desktop = self.config.desktop
        items = []

        if desktop.allow_dbus:
            items.append("D-Bus")

        if desktop.allow_display:
            display_info = detect_display_server()
            if display_info["type"]:
                items.append(display_info["type"].upper())

        if desktop.bind_user_config:
            items.append("~/.config")

        if items:
            lines.append(f"• Desktop: {', '.join(items)}")

    def _add_filesystem_summary(self, lines: list[str]) -> None:
        """Add filesystem summary."""
        fs = self.config.filesystem

        # System paths
        bound_sys = []
        for attr, path in fs.SYSTEM_PATHS.items():
            if getattr(fs, attr):
                bound_sys.append(path)
        if bound_sys:
            lines.append(f"• System paths (read-only): {', '.join(bound_sys)}")

        # User directories
        if self.config.bound_dirs:
            ro_dirs = [str(d.path) for d in self.config.bound_dirs if d.readonly]
            rw_dirs = [str(d.path) for d in self.config.bound_dirs if not d.readonly]
            if ro_dirs:
                lines.append(f"• User directories (read-only): {', '.join(ro_dirs)}")
            if rw_dirs:
                lines.append(f"• User directories (read-write): {', '.join(rw_dirs)}")

        # Virtual filesystems
        vfs = []
        if fs.dev_mode == "minimal":
            vfs.append("/dev (minimal)")
        elif fs.dev_mode == "full":
            vfs.append("/dev (full host access)")

        if fs.mount_proc:
            vfs.append("/proc")

        if fs.mount_tmp:
            tmp_desc = "/tmp (ephemeral"
            if fs.tmpfs_size:
                tmp_desc += f", max {fs.tmpfs_size}"
            tmp_desc += ")"
            vfs.append(tmp_desc)

        if vfs:
            lines.append(f"• Virtual filesystems: {', '.join(vfs)}")

    def _add_overlay_summary(self, lines: list[str]) -> None:
        """Add overlay summary."""
        if self.config.overlays:
            lines.append(f"• Overlays ({len(self.config.overlays)}):")
            for ov in self.config.overlays:
                if ov.mode == "tmpfs":
                    lines.append(f"    - {ov.source} → {ov.dest} (tmpfs, discarded on exit)")
                else:
                    lines.append(f"    - {ov.source} → {ov.dest} (persistent to {ov.write_dir})")

    def _add_environment_summary(self, lines: list[str]) -> None:
        """Add environment summary."""
        env = self.config.environment

        if env.clear_env:
            lines.append(f"• Environment: CLEARED, keeping {len(env.keep_env_vars)} vars")
        elif env.unset_env_vars:
            lines.append(f"• Environment: inherited minus {len(env.unset_env_vars)} removed vars")
        else:
            lines.append("• Environment: fully inherited from parent")

        if env.custom_env_vars:
            lines.append(f"• Custom env vars: {', '.join(env.custom_env_vars.keys())}")

    def _add_namespace_summary(self, lines: list[str]) -> None:
        """Add namespace isolation summary."""
        ns = self.config.namespace
        proc = self.config.process

        isolation = []
        for name, field in NamespaceConfig.get_ui_fields().items():
            if name == "disable_userns":
                continue  # Handled separately
            value = getattr(ns, name)
            if value:
                isolation.append(field.summary)

        # Special case: as_pid_1 implies PID namespace
        if proc.as_pid_1 and not ns.unshare_pid:
            isolation.append(f"{NamespaceConfig.unshare_pid.summary} (required by as-pid-1)")

        if isolation:
            lines.append("• Isolation namespaces:")
            for item in isolation:
                lines.append(f"    - {item}")

        # User/group mapping
        if ns.unshare_user:
            lines.append(f"• User mapping: UID {proc.uid}, GID {proc.gid}")

        # Advanced
        if ns.disable_userns:
            lines.append(f"• {NamespaceConfig.disable_userns.summary}")

    def _add_capability_summary(self, lines: list[str]) -> None:
        """Add capability drop summary."""
        if self.config.drop_caps:
            lines.append("• Sandbox CANNOT:")
            for cap in sorted(self.config.drop_caps):
                desc = self.ALL_CAPS.get(cap, "unknown")
                lines.append(f"    ✗ {desc.capitalize()}")

    def _add_process_summary(self, lines: list[str]) -> None:
        """Add process behavior summary."""
        proc = self.config.process
        env = self.config.environment

        items = []
        if proc.die_with_parent:
            items.append("dies with parent")
        if proc.new_session:
            items.append("new session")
        if proc.as_pid_1:
            items.append("runs as PID 1 (init)")
        if proc.chdir:
            items.append(f"workdir: {proc.chdir}")
        if env.custom_hostname:
            items.append(f"hostname: {env.custom_hostname}")

        if items:
            lines.append(f"• Process: {', '.join(items)}")
