"""Widget ID constants for the TUI.

Using constants prevents typos and makes refactoring easier.
"""


def css(widget_id: str) -> str:
    """Return a CSS selector for a widget ID.

    Usage:
        from ui.ids import css, STATUS_BAR
        self.query_one(css(STATUS_BAR), Static)
    """
    return f"#{widget_id}"

# Container IDs
HEADER_CONTAINER = "header-container"
HEADER_TITLE = "header-title"
MAIN_CONTENT = "main-content"
MAIN_SWITCHER = "main-switcher"
CONFIG_TABS = "config-tabs"
SUMMARY_VIEW = "summary-view"
PROFILES_VIEW = "profiles-view"
FOOTER_BUTTONS = "footer-buttons"
STATUS_BAR = "status-bar"

# Directory tab IDs
DIRS_TAB_CONTENT = "dirs-tab-content"
DIR_BROWSER_CONTAINER = "dir-browser-container"
DIR_TREE = "dir-tree"
DIR_NAV_BUTTONS = "dir-nav-buttons"
PATH_INPUT_ROW = "path-input-row"
PATH_INPUT = "path-input"
ADD_PATH_BTN = "add-path-btn"
ADD_DIR_BTN = "add-dir-btn"
PARENT_DIR_BTN = "parent-dir-btn"
BOUND_DIRS_CONTAINER = "bound-dirs-container"
BOUND_DIRS_LIST = "bound-dirs-list"

# Environment tab IDs
ENV_TAB_CONTENT = "env-tab-content"
ENV_BUTTONS_ROW = "env-buttons-row"
ENV_GRID_SCROLL = "env-grid-scroll"
ENV_GRID = "env-grid"
TOGGLE_CLEAR_BTN = "toggle-clear-btn"
ADD_ENV_BTN = "add-env-btn"
ENV_HINT = "env-hint"

# Overlays tab IDs
OVERLAYS_TAB_CONTENT = "overlays-tab-content"
OVERLAYS_LIST = "overlays-list"
OVERLAY_HEADER = "overlay-header"
ADD_OVERLAY_BTN = "add-overlay-btn"
OVERLAY_HINT = "overlay-hint"

# Filesystem tab IDs
FILESYSTEMS_TAB_CONTENT = "filesystems-tab-content"
OPTIONS_GRID = "options-grid"

# Sandbox tab IDs
SANDBOX_TAB_CONTENT = "sandbox-tab-content"
UID_GID_OPTIONS = "uid-gid-options"
USERNAME_OPTIONS = "username-options"
VIRTUAL_USER_OPTIONS = "virtual-user-options"
OPT_SYNTHETIC_PASSWD = "opt-synthetic-passwd"
OPT_OVERLAY_HOME = "opt-overlay-home"

# Summary tab IDs
SUMMARY_TAB_CONTENT = "summary-tab-content"
SUMMARY_HEADER = "summary-header"
SECURITY_WARNING = "security-warning"
COMMAND_PREVIEW = "command-preview"
EXPLANATION = "explanation"

# Profiles tab IDs
PROFILES_TAB_CONTENT = "profiles-tab-content"
PROFILES_LIST = "profiles-list"
SAVE_PROFILE_BTN = "save-profile-btn"
LOAD_PROFILE_BTN = "load-profile-btn"
PROFILE_NAME_INPUT = "profile-name-input"
LOAD_PROFILE_PATH = "load-profile-path"

# Action buttons
PROFILES_BTN = "profiles-btn"
SUMMARY_BTN = "summary-btn"
EXECUTE_BTN = "execute-btn"
CANCEL_BTN = "cancel-btn"

# Option checkbox/input IDs (used by UIField and FieldMapping)
# Filesystem options
OPT_PROC = "opt-proc"
OPT_TMP = "opt-tmp"
OPT_TMPFS_SIZE = "opt-tmpfs-size"
OPT_USR = "opt-usr"
OPT_BIN = "opt-bin"
OPT_LIB = "opt-lib"
OPT_LIB64 = "opt-lib64"
OPT_SBIN = "opt-sbin"
OPT_ETC = "opt-etc"

# Network options
OPT_NET = "opt-net"
OPT_RESOLV_CONF = "opt-resolv-conf"
OPT_SSL_CERTS = "opt-ssl-certs"

# Desktop options
OPT_DBUS = "opt-dbus"
OPT_DISPLAY = "opt-display"
OPT_USER_CONFIG = "opt-user-config"

# Namespace options
OPT_UNSHARE_USER = "opt-unshare-user"
OPT_UNSHARE_PID = "opt-unshare-pid"
OPT_UNSHARE_IPC = "opt-unshare-ipc"
OPT_UNSHARE_UTS = "opt-unshare-uts"
OPT_UNSHARE_CGROUP = "opt-unshare-cgroup"
OPT_DISABLE_USERNS = "opt-disable-userns"

# Process options
OPT_DIE_WITH_PARENT = "opt-die-with-parent"
OPT_NEW_SESSION = "opt-new-session"
OPT_AS_PID_1 = "opt-as-pid-1"
OPT_CHDIR = "opt-chdir"
OPT_HOSTNAME = "opt-hostname"
OPT_UID = "opt-uid"
OPT_GID = "opt-gid"
OPT_USERNAME = "opt-username"

# Dev mode widget IDs
DEV_MODE_BTN = "dev-mode-btn"
DEV_MODE_DESC = "dev-mode-desc"

# Add env dialog IDs
ADD_ENV_DIALOG = "add-env-dialog"
ENV_DIALOG_TABS = "env-dialog-tabs"
DIALOG_BUTTONS = "dialog-buttons"
ENV_ROWS_CONTAINER = "env-rows-container"
DOTENV_CONTAINER = "dotenv-container"
DOTENV_TREE = "dotenv-tree"
DOTENV_PREVIEW = "dotenv-preview"
DOTENV_PARENT_BTN = "dotenv-parent-btn"
ADD_BTN = "add-btn"

# Note: CANCEL_BTN is shared with footer, already defined above

# Quick shortcuts section (directories tab)
QUICK_SHORTCUTS_SECTION = "quick-shortcuts-section"

# Network filtering tab IDs
NETWORK_TAB_CONTENT = "network-tab-content"
NETWORK_MODE_RADIO = "network-mode-radio"
PASTA_STATUS = "pasta-status"
HOSTNAME_MODE_RADIO = "hostname-mode-radio"
HOSTNAME_LIST = "hostname-list"
HOSTNAME_INPUT = "hostname-input"
ADD_HOSTNAME_BTN = "add-hostname-btn"
IP_MODE_RADIO = "ip-mode-radio"
CIDR_LIST = "cidr-list"
CIDR_INPUT = "cidr-input"
ADD_CIDR_BTN = "add-cidr-btn"
# Expose ports (sandbox → host)
EXPOSE_PORT_LIST = "expose-port-list"
EXPOSE_PORT_INPUT = "expose-port-input"
ADD_EXPOSE_PORT_BTN = "add-expose-port-btn"
# Host ports (host → sandbox)
HOST_PORT_LIST = "host-port-list"
HOST_PORT_INPUT = "host-port-input"
ADD_HOST_PORT_BTN = "add-host-port-btn"
