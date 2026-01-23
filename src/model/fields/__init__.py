"""UIField definitions organized by domain.

This package contains all UIField definitions split by functional area.
"""

# Virtual Filesystems
from model.fields.vfs import (
    dev_mode,
    mount_proc,
    mount_tmp,
    tmpfs_size,
)

# System Paths
from model.fields.system_paths import (
    bind_usr,
    bind_bin,
    bind_lib,
    bind_lib64,
    bind_sbin,
    bind_etc,
)

# User Identity
from model.fields.user import (
    unshare_user,
    synthetic_passwd,
    overlay_home,
    uid_field,
    gid_field,
    username_field,
)

# Isolation (Namespaces)
from model.fields.isolation import (
    unshare_pid,
    unshare_ipc,
    unshare_uts,
    unshare_cgroup,
    disable_userns,
)

# Process
from model.fields.process import (
    die_with_parent,
    new_session,
    as_pid_1,
    chdir,
)

# Network
from model.fields.network import (
    share_net,
    bind_resolv_conf,
    bind_ssl_certs,
)

# Desktop Integration
from model.fields.desktop import (
    allow_dbus,
    allow_display,
    bind_user_config,
)

# Environment
from model.fields.environment import (
    clear_env,
    custom_hostname,
    keep_env_vars_field,
    unset_env_vars_field,
    custom_env_vars_field,
)
