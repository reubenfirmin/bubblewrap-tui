"""Process control configuration model."""

import os

from model.ui_field import ConfigBase, Field, UIField


class ProcessConfig(ConfigBase):
    """Process control settings for the sandbox."""

    die_with_parent = UIField(
        bool, True, "opt-die-with-parent",
        "Kill with parent", "Dies when terminal closes",
        bwrap_flag="--die-with-parent",
    )
    new_session = UIField(
        bool, True, "opt-new-session",
        "New session", "Prevents terminal escape attacks, but disables job control",
        bwrap_flag="--new-session",
    )
    as_pid_1 = UIField(
        bool, False, "opt-as-pid-1",
        "Run as PID 1", "Command runs as init process in PID namespace",
        bwrap_flag="--as-pid-1",
    )
    chdir = UIField(
        str, "", "opt-chdir",
        "Working dir", "Directory to start in",
        bwrap_args=lambda v: ["--chdir", v] if v else [],
    )

    # User/group mapping (used when unshare_user is True)
    # These don't have standard checkboxes - they're input fields shown conditionally
    uid = Field(int, default_factory=os.getuid)
    gid = Field(int, default_factory=os.getgid)
