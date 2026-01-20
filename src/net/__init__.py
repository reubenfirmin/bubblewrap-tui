"""Network filtering module.

This module provides network filtering capabilities using pasta for
user-mode networking and iptables for packet filtering.

Architecture:
    pasta (spawn mode) creates a network namespace and runs bwrap inside.
    iptables rules are applied to filter traffic within the namespace.
"""

from net.iptables import (
    check_iptables,
    find_iptables,
    generate_init_script,
    generate_iptables_rules,
)
from net.pasta import (
    check_pasta,
    execute_with_pasta,
    generate_pasta_args,
    get_install_instructions,
    get_pasta_status,
)
from net.utils import (
    detect_distro,
    get_www_variant,
    is_ipv6,
    resolve_hostname,
    validate_cidr,
    validate_port,
)

# Alias for backwards compatibility
execute_with_network_filter = execute_with_pasta

__all__ = [
    # pasta
    "check_pasta",
    "execute_with_pasta",
    "execute_with_network_filter",  # backwards compat
    "generate_pasta_args",
    "get_install_instructions",
    "get_pasta_status",
    # iptables
    "check_iptables",
    "find_iptables",
    "generate_init_script",
    "generate_iptables_rules",
    # utils
    "detect_distro",
    "get_www_variant",
    "is_ipv6",
    "resolve_hostname",
    "validate_cidr",
    "validate_port",
]
