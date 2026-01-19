"""Bubblewrap command serialization and summarization.

Uses the group-based architecture for color-matched command/summary display.
"""

from __future__ import annotations

import shlex
from typing import TYPE_CHECKING

from model.groups import COLORS, DEFAULT_COLOR

if TYPE_CHECKING:
    from model.sandbox_config import SandboxConfig


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


class BubblewrapSerializer:
    """Serializes SandboxConfig to bwrap command-line arguments."""

    def __init__(self, config: SandboxConfig) -> None:
        self.config = config

    def serialize(self) -> list[str]:
        """Build the complete bwrap command."""
        args = ["bwrap"]

        # Get args from all groups
        for group in self.config.get_all_groups():
            # Special handling for process group (needs isolation group)
            if group.name == "process":
                args.extend(self._get_process_args())
            else:
                args.extend(group.to_args())

        # Overlays
        for overlay in self.config.overlays:
            args.extend(overlay.to_args())

        # Capability drops
        for cap in self.config.drop_caps:
            args.extend(["--cap-drop", cap])

        # Bound directories
        for bound_dir in self.config.bound_dirs:
            args.extend(bound_dir.to_args())

        # Command separator and command
        args.append("--")
        args.extend(self.config.command)

        return args

    def _get_process_args(self) -> list[str]:
        """Get process args (needs isolation group for user namespace check)."""
        from model.groups import _process_to_args
        return _process_to_args(self.config._process_group, self.config._isolation_group)

    def serialize_colored(self) -> str:
        """Build the command with Rich color markup, rotating colors by group."""
        parts = ["[bold]bwrap[/bold]"]
        color_idx = 0

        # Process groups in order
        for group in self.config.get_all_groups():
            # Special handling for process group
            if group.name == "process":
                args = self._get_process_args()
            else:
                args = group.to_args()

            if not args:
                continue

            color = COLORS[color_idx % len(COLORS)]
            color_idx += 1

            for arg in args:
                parts.append(f"[{color}]{shlex.quote(arg)}[/]")

        # Overlays (get their own color)
        overlay_args = []
        for overlay in self.config.overlays:
            overlay_args.extend(overlay.to_args())
        if overlay_args:
            color = COLORS[color_idx % len(COLORS)]
            color_idx += 1
            for arg in overlay_args:
                parts.append(f"[{color}]{shlex.quote(arg)}[/]")

        # Capability drops (get their own color)
        cap_args = []
        for cap in self.config.drop_caps:
            cap_args.extend(["--cap-drop", cap])
        if cap_args:
            color = COLORS[color_idx % len(COLORS)]
            color_idx += 1
            for arg in cap_args:
                parts.append(f"[{color}]{shlex.quote(arg)}[/]")

        # Bound directories (get their own color)
        dir_args = []
        for bound_dir in self.config.bound_dirs:
            dir_args.extend(bound_dir.to_args())
        if dir_args:
            color = COLORS[color_idx % len(COLORS)]
            color_idx += 1
            for arg in dir_args:
                parts.append(f"[{color}]{shlex.quote(arg)}[/]")

        # Separator and command (white, not colored - it's what the user asked to run)
        parts.append("[dim]--[/]")
        for arg in self.config.command:
            parts.append(shlex.quote(arg))

        return " ".join(parts)


class BubblewrapSummarizer:
    """Generates human-readable summaries of SandboxConfig."""

    def __init__(self, config: SandboxConfig) -> None:
        self.config = config

    def summarize(self) -> str:
        """Generate a human-readable explanation of the sandbox."""
        lines: list[str] = []

        def _add_bulleted(summary: str) -> None:
            """Add summary lines with bullets for top-level items only."""
            for line in summary.split("\n"):
                if line and not line[0].isspace():
                    lines.append(f"• {line}")
                else:
                    lines.append(line)

        # Get summaries from all groups
        for group in self.config.get_all_groups():
            # Special handling for process group
            if group.name == "process":
                summary = self._get_process_summary()
            else:
                summary = group.to_summary()

            if summary:
                _add_bulleted(summary)

        # Overlays
        if self.config.overlays:
            lines.append(f"• Overlays ({len(self.config.overlays)}):")
            for ov in self.config.overlays:
                if ov.mode == "tmpfs":
                    lines.append(f"  - {ov.source} → {ov.dest}: Changes stored in RAM, discarded on exit")
                else:
                    lines.append(f"  - {ov.source} → {ov.dest}: Changes saved to {ov.write_dir}, originals untouched")

        # Capabilities
        if self.config.drop_caps:
            lines.append("• Sandbox CANNOT:")
            for cap in sorted(self.config.drop_caps):
                desc = ALL_CAPS.get(cap, "unknown")
                lines.append(f"  ✗ {desc.capitalize()}")

        # Bound directories
        if self.config.bound_dirs:
            ro_dirs = [str(d.path) for d in self.config.bound_dirs if d.readonly]
            rw_dirs = [str(d.path) for d in self.config.bound_dirs if not d.readonly]
            if ro_dirs:
                lines.append(f"• User directories (read-only): {', '.join(ro_dirs)} — sandbox cannot modify")
            if rw_dirs:
                lines.append(f"• User directories (read-write): {', '.join(rw_dirs)} — sandbox can modify these files")

        # Command
        lines.append(f"• Running: {' '.join(self.config.command)}")

        return "\n".join(lines)

    def _get_process_summary(self) -> str | None:
        """Get process summary (needs isolation and environment groups)."""
        from model.groups import _process_to_summary
        return _process_to_summary(
            self.config._process_group,
            self.config._isolation_group,
            self.config._environment_group,
        )

    def summarize_colored(self) -> str:
        """Generate a colored summary matching command group colors."""
        lines: list[str] = []
        color_idx = 0

        # Process groups in order (matching serializer)
        for group in self.config.get_all_groups():
            # Special handling for process group
            if group.name == "process":
                args = BubblewrapSerializer(self.config)._get_process_args()
                summary = self._get_process_summary()
            else:
                args = group.to_args()
                summary = group.to_summary()

            if not summary:
                continue

            # Check if this group has args (for color selection)
            if args:
                color = COLORS[color_idx % len(COLORS)]
                color_idx += 1
            else:
                color = DEFAULT_COLOR

            # Handle multi-line summaries - add bullets to top-level lines only
            for line in summary.split("\n"):
                # Add bullet to lines that don't start with whitespace (not nested items)
                if line and not line[0].isspace():
                    lines.append(f"[{color}]• {line}[/]")
                else:
                    lines.append(f"[{color}]{line}[/]")

        # Overlays
        if self.config.overlays:
            color = COLORS[color_idx % len(COLORS)]
            color_idx += 1
            lines.append(f"[{color}]• Overlays ({len(self.config.overlays)}):[/]")
            for ov in self.config.overlays:
                if ov.mode == "tmpfs":
                    lines.append(f"[{color}]  - {ov.source} → {ov.dest}: Changes stored in RAM, discarded on exit[/]")
                else:
                    lines.append(f"[{color}]  - {ov.source} → {ov.dest}: Changes saved to {ov.write_dir}, originals untouched[/]")

        # Capabilities
        if self.config.drop_caps:
            color = COLORS[color_idx % len(COLORS)]
            color_idx += 1
            lines.append(f"[{color}]• Sandbox CANNOT:[/]")
            for cap in sorted(self.config.drop_caps):
                desc = ALL_CAPS.get(cap, "unknown")
                lines.append(f"[{color}]  ✗ {desc.capitalize()}[/]")

        # Bound directories
        if self.config.bound_dirs:
            color = COLORS[color_idx % len(COLORS)]
            color_idx += 1
            ro_dirs = [str(d.path) for d in self.config.bound_dirs if d.readonly]
            rw_dirs = [str(d.path) for d in self.config.bound_dirs if not d.readonly]
            if ro_dirs:
                lines.append(f"[{color}]• User directories (read-only): {', '.join(ro_dirs)} — sandbox cannot modify[/]")
            if rw_dirs:
                lines.append(f"[{color}]• User directories (read-write): {', '.join(rw_dirs)} — sandbox can modify these files[/]")

        # Command (white, not colored - it's what the user asked to run)
        lines.append(f"• Running: {' '.join(self.config.command)}")

        return "\n".join(lines)
