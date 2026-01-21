"""UIField definitions for Process group."""

from model.ui_field import UIField


def _named(name: str, field: UIField) -> UIField:
    """Set the name attribute on a UIField and return it."""
    field.name = name
    return field


die_with_parent = _named("die_with_parent", UIField(
    bool, True, "opt-die-with-parent",
    "Kill with parent", "Dies when terminal closes",
    bwrap_flag="--die-with-parent",
))

new_session = _named("new_session", UIField(
    bool, True, "opt-new-session",
    "New session", "Prevents terminal escape attacks, but disables job control",
    bwrap_flag="--new-session",
))

as_pid_1 = _named("as_pid_1", UIField(
    bool, False, "opt-as-pid-1",
    "Run as PID 1", "Command runs as init process in PID namespace",
    bwrap_flag="--as-pid-1",
))

chdir = _named("chdir", UIField(
    str, "", "opt-chdir",
    "Working dir", "Directory to start in",
    bwrap_args=lambda v: ["--chdir", v] if v else [],
))
