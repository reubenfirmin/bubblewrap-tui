"""Network module for filtering and auditing.

This module provides network capabilities using pasta for user-mode networking:
- FILTER mode: iptables rules for traffic filtering
- AUDIT mode: pcap capture for traffic analysis

Architecture:
    pasta (spawn mode) creates a network namespace and runs bwrap inside.
    For filtering, iptables rules are applied within the namespace.
    For auditing, traffic is captured to pcap and analyzed after exit.
"""

from net.audit import (
    AuditResult,
    parse_pcap,
    print_audit_summary,
)
from net.iptables import (
    check_iptables,
    find_iptables,
    generate_init_script,
    generate_iptables_rules,
)
from net.pasta import (
    check_pasta,
    execute_with_audit,
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
    "execute_with_audit",
    "execute_with_pasta",
    "execute_with_network_filter",  # backwards compat
    "generate_pasta_args",
    "get_install_instructions",
    "get_pasta_status",
    # audit
    "AuditResult",
    "parse_pcap",
    "print_audit_summary",
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
