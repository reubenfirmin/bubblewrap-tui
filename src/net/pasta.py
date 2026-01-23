"""pasta network namespace wrapper.

pasta (part of passt) provides user-mode networking for sandboxes.
It creates a network namespace and provides connectivity without
requiring special privileges.

In spawn mode, pasta creates a new user+network namespace and runs
the given command inside. This is simpler than slirp4netns and
requires no CAP_SYS_ADMIN.

This module re-exports from the split submodules for backwards compatibility.
"""

from __future__ import annotations

# Installation detection
from net.pasta_install import (
    check_pasta,
    get_install_instructions,
    get_pasta_status,
)

# Command argument generation
from net.pasta_args import (
    generate_pasta_args,
    prepare_bwrap_command,
)

# Network filtering validation
from net.filtering import (
    validate_filtering_requirements,
)

# Execution functions
from net.pasta_exec import (
    execute_with_pasta,
    execute_with_audit,
)

# Legacy aliases with underscore prefix for backwards compatibility
_validate_filtering_requirements = validate_filtering_requirements
_prepare_bwrap_command = prepare_bwrap_command

__all__ = [
    # Installation
    "check_pasta",
    "get_install_instructions",
    "get_pasta_status",
    # Arguments
    "generate_pasta_args",
    "prepare_bwrap_command",
    # Filtering
    "validate_filtering_requirements",
    # Execution
    "execute_with_pasta",
    "execute_with_audit",
    # Legacy aliases
    "_validate_filtering_requirements",
    "_prepare_bwrap_command",
]
