"""UIField definitions for Environment group."""

from model.ui_field import UIField, Field


def _named(name: str, field: UIField) -> UIField:
    """Set the name attribute on a UIField and return it."""
    field.name = name
    return field


def _validate_hostname(value: str) -> str | None:
    """Lazy import wrapper for validate_hostname to avoid circular imports."""
    from controller.validators import validate_hostname
    return validate_hostname(value)


clear_env = _named("clear_env", UIField(
    bool, False, "toggle-clear-btn",
    "Clear environment", "Start with empty environment",
    bwrap_flag="--clearenv",
))

custom_hostname = _named("custom_hostname", UIField(
    str, "", "opt-hostname",
    "Custom hostname", "Hostname inside the sandbox (1-63 chars, alphanumeric/hyphens)",
    bwrap_args=lambda v: ["--hostname", v] if v else [],
    value_transform=_validate_hostname,
))

# Data fields for environment
keep_env_vars_field = Field(set, default_factory=set)
unset_env_vars_field = Field(set, default_factory=set)
custom_env_vars_field = Field(dict, default_factory=dict)
