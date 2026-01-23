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

    def get_virtual_user_data(self) -> list[tuple[str, str]]:
        """Get virtual user file data that needs to be passed via FDs.

        Returns list of (content, dest_path) tuples for files to inject.
        """
        synthetic_passwd = self.config._user_group.get("synthetic_passwd")
        username = self.config._user_group.get("username")
        uid = self.config._user_group.get("uid")
        gid = self.config._user_group.get("gid")

        # Only generate when synthetic_passwd enabled and username set
        if not synthetic_passwd or not username:
            return []

        # Use /root for uid 0, otherwise /home/{username}
        home = "/root" if uid == 0 else f"/home/{username}"

        # Generate passwd: username:x:uid:gid::{home}:/bin/sh
        passwd_content = f"{username}:x:{uid}:{gid}::{home}:/bin/sh\n"
        # Generate group: username:x:gid:
        group_content = f"{username}:x:{gid}:\n"

        return [
            (passwd_content, "/etc/passwd"),
            (group_content, "/etc/group"),
        ]

    def _has_home_overlay(self, home: str) -> bool:
        """Check if either the user's home or /root has an overlay.

        /root is checked because it's the default home for UID 0.
        When synthetic_passwd is enabled, we need to know if there's already
        an overlay handling home directory creation to avoid creating duplicate
        directories.
        """
        for ov in self.config.overlays:
            if ov.dest == home or ov.dest == "/root":
                return True
        return False

    def _serialize_virtual_user_args(self, file_map: dict[str, str]) -> list[str]:
        """Serialize virtual user args using pre-created temp files.

        Args:
            file_map: Mapping of dest_path -> source_file_path

        Returns:
            bwrap args for virtual user setup
        """
        synthetic_passwd = self.config._user_group.get("synthetic_passwd")
        username = self.config._user_group.get("username")
        uid = self.config._user_group.get("uid")

        if not synthetic_passwd or not username:
            return []

        # Use /root for uid 0, otherwise /home/{username}
        home = "/root" if uid == 0 else f"/home/{username}"
        args = []

        # Create /etc directory for passwd/group
        args.extend(["--dir", "/etc"])

        # Bind passwd/group from temp files
        if "/etc/passwd" in file_map:
            args.extend(["--ro-bind", file_map["/etc/passwd"], "/etc/passwd"])
        if "/etc/group" in file_map:
            args.extend(["--ro-bind", file_map["/etc/group"], "/etc/group"])

        # If no home overlay exists, we need to create /home/{user}
        # If there's an overlay for home, it handles creating the directory
        if not self._has_home_overlay(home):
            args.extend(["--dir", "/home"])
            args.extend(["--dir", home])
            # Set HOME environment variable
            args.extend(["--setenv", "HOME", home])

        return args

    def serialize(self, file_map: dict[str, str] | None = None) -> list[str]:
        """Build the complete bwrap command.

        Args:
            file_map: Optional mapping of dest_path -> source_file_path for virtual user files
        """
        args = ["bwrap"]

        # Get args from all groups
        for group in self.config.get_all_groups():
            # Special handling for process group (needs isolation group)
            if group.name == "process":
                args.extend(self._get_process_args())
            # Special handling for network group (needs network_filter)
            elif group.name == "network":
                args.extend(self._get_network_args())
            else:
                args.extend(group.to_args())

        # Bound directories (must come before overlays so overlays can override)
        for bound_dir in self.config.bound_dirs:
            args.extend(bound_dir.to_args())

        # Overlays (override bound directories for specific subdirectories)
        for overlay in self.config.overlays:
            args.extend(overlay.to_args())

        # Virtual user setup (must come AFTER overlays so bindings layer on top)
        if file_map:
            args.extend(self._serialize_virtual_user_args(file_map))

        # Capability drops
        for cap in self.config.drop_caps:
            args.extend(["--cap-drop", cap])

        # Command separator and command
        args.append("--")
        args.extend(self.config.command)

        return args

    def _get_process_args(self) -> list[str]:
        """Get process args (needs isolation group for user namespace check)."""
        from model.groups import _process_to_args
        return _process_to_args(self.config._process_group, self.config._isolation_group)

    def _get_network_args(self) -> list[str]:
        """Get network args (checks network filtering)."""
        from model.groups import _network_to_args
        return _network_to_args(self.config._network_group, self.config.network_filter)

    def serialize_colored(self) -> str:
        """Build the command with Rich color markup, rotating colors by group."""
        parts = ["[bold]bwrap[/bold]"]
        color_idx = 0

        # Process groups in order
        for group in self.config.get_all_groups():
            # Special handling for process group
            if group.name == "process":
                args = self._get_process_args()
            # Special handling for network group
            elif group.name == "network":
                args = self._get_network_args()
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

        result = " ".join(parts)

        # Add pasta command if network filtering is active
        nf = self.config.network_filter
        if nf.requires_pasta():
            from net.pasta import generate_pasta_args
            color = COLORS[color_idx % len(COLORS)]
            pasta_parts = [f"[bold {color}]pasta[/]"]
            pasta_args = generate_pasta_args(nf)
            # Skip first element (pasta itself) since we handle it specially
            for arg in pasta_args[1:]:
                pasta_parts.append(f"[{color}]{arg}[/]")
            # Add placeholder for the bwrap command
            pasta_parts.append("[dim]--[/]")
            pasta_parts.append("[dim]<bwrap...>[/]")
            result += "\n\n" + " ".join(pasta_parts)

        return result


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
            # Special handling for isolation group
            elif group.name == "isolation":
                summary = self._get_isolation_summary()
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

        # Virtual files (synthetic passwd/group, etc.)
        virtual_files = self._get_virtual_files_summary()
        if virtual_files:
            lines.append("• Virtual files injected:")
            for vf_line in virtual_files:
                lines.append(f"  - {vf_line}")

        # Network filtering
        nf = self.config.network_filter
        if nf.requires_pasta():
            lines.append("• Network filtering (pasta):")
            for summary_line in nf.get_filtering_summary():
                lines.append(f"  - {summary_line}")

        # Command
        lines.append(f"• Running: {' '.join(self.config.command)}")

        return "\n".join(lines)

    def _get_process_summary(self) -> str | None:
        """Get process summary (needs environment group)."""
        from model.groups import _process_to_summary
        return _process_to_summary(
            self.config._process_group,
            self.config._environment_group,
        )

    def _get_isolation_summary(self) -> str | None:
        """Get isolation summary."""
        from model.groups import _isolation_to_summary
        return _isolation_to_summary(
            self.config._isolation_group,
            self.config.network_filter,
        )

    def _get_virtual_files_summary(self) -> list[str]:
        """Get summary of virtual files that will be injected."""
        from virtual_files import create_virtual_files
        vfiles = create_virtual_files(self.config)
        return vfiles.get_summary()

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
            # Special handling for isolation group
            elif group.name == "isolation":
                args = group.to_args()
                summary = self._get_isolation_summary()
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

        # Network filtering
        nf = self.config.network_filter
        if nf.requires_pasta():
            color = COLORS[color_idx % len(COLORS)]
            color_idx += 1
            lines.append(f"[{color}]• Network filtering (pasta):[/]")
            for summary_line in nf.get_filtering_summary():
                lines.append(f"[{color}]  - {summary_line}[/]")

        # Command (white, not colored - it's what the user asked to run)
        lines.append(f"• Running: {' '.join(self.config.command)}")

        return "\n".join(lines)
