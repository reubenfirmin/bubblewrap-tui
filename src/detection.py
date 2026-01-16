"""System detection utilities for bui."""

import os
from pathlib import Path


def find_ssl_cert_paths() -> list[str]:
    """Dynamically find SSL certificate paths on this system."""
    candidates = [
        "/etc/ssl/certs",
        "/etc/ssl/cert.pem",
        "/etc/pki/tls/certs",
        "/etc/pki/ca-trust/extracted",
        "/etc/ca-certificates",
        "/usr/share/ca-certificates",
        "/usr/local/share/ca-certificates",
    ]
    paths = []
    for candidate in candidates:
        p = Path(candidate)
        if p.exists():
            # Resolve symlinks to get the real path
            resolved = p.resolve()
            if str(resolved) not in paths:
                paths.append(str(resolved))
            # Also include the original if it's a symlink (for apps that expect it)
            if p.is_symlink() and str(p) not in paths:
                paths.append(str(p))
    return paths


def detect_display_server() -> dict[str, list[str]]:
    """Detect what display server is running and return paths to bind."""
    result = {"type": None, "paths": [], "env_vars": []}
    uid = os.getuid()

    # Check Wayland first (preferred on modern systems)
    wayland_display = os.environ.get("WAYLAND_DISPLAY")
    if wayland_display:
        result["type"] = "wayland"
        result["env_vars"].append("WAYLAND_DISPLAY")
        # Wayland socket is in XDG_RUNTIME_DIR
        runtime_dir = os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{uid}")
        socket_path = Path(runtime_dir) / wayland_display
        if socket_path.exists():
            result["paths"].append(str(socket_path))
        # Some apps also need these Wayland-related env vars
        for var in ["XDG_RUNTIME_DIR", "XDG_SESSION_TYPE"]:
            if var in os.environ and var not in result["env_vars"]:
                result["env_vars"].append(var)

    # Check X11
    display = os.environ.get("DISPLAY")
    if display:
        if result["type"]:
            result["type"] = "both"
        else:
            result["type"] = "x11"
        result["env_vars"].append("DISPLAY")
        # X11 sockets
        x11_dir = Path("/tmp/.X11-unix")
        if x11_dir.exists():
            result["paths"].append(str(x11_dir))
        # Xauthority for authentication
        xauth = os.environ.get("XAUTHORITY", str(Path.home() / ".Xauthority"))
        if Path(xauth).exists():
            result["paths"].append(xauth)
            result["env_vars"].append("XAUTHORITY")

    return result


def detect_dbus_session() -> list[str]:
    """Detect D-Bus session bus paths."""
    paths = []
    uid = os.getuid()

    # Standard session bus socket location
    runtime_dir = os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{uid}")
    bus_path = Path(runtime_dir) / "bus"
    if bus_path.exists():
        paths.append(str(bus_path))

    # Also check DBUS_SESSION_BUS_ADDRESS for non-standard setups
    dbus_addr = os.environ.get("DBUS_SESSION_BUS_ADDRESS", "")
    if dbus_addr.startswith("unix:path="):
        socket_path = dbus_addr.split("=")[1].split(",")[0]
        if Path(socket_path).exists() and socket_path not in paths:
            paths.append(socket_path)

    return paths


def find_dns_paths() -> list[str]:
    """Dynamically find DNS configuration paths on this system."""
    paths = []
    resolv = Path("/etc/resolv.conf")
    if resolv.exists():
        # Get the real path (might be symlink to /run/systemd/resolve/stub-resolv.conf etc)
        resolved = resolv.resolve()
        paths.append(str(resolved))
        # Also bind the symlink itself if different
        if resolv.is_symlink():
            paths.append("/etc/resolv.conf")
        # On systemd, we might also need the parent dir for related files
        if "systemd" in str(resolved):
            parent = resolved.parent
            if parent.exists() and str(parent) not in paths:
                paths.append(str(parent))
    # Also check nsswitch.conf for name resolution config
    nsswitch = Path("/etc/nsswitch.conf")
    if nsswitch.exists():
        paths.append(str(nsswitch))
    return paths
