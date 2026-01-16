"""Environment configuration model."""

from model.ui_field import ConfigBase, Field, UIField


class EnvironmentConfig(ConfigBase):
    """Environment variable settings for the sandbox."""

    clear_env = UIField(
        bool, False, "toggle-clear-btn",
        "Clear environment", "Start with empty environment",
        bwrap_flag="--clearenv",
    )
    custom_hostname = UIField(
        str, "", "opt-hostname",
        "Custom hostname", "Hostname inside the sandbox",
        bwrap_args=lambda v: ["--hostname", v] if v else [],
    )

    # Data fields - managed programmatically, not via checkboxes
    keep_env_vars = Field(set, default_factory=set)
    unset_env_vars = Field(set, default_factory=set)
    custom_env_vars = Field(dict, default_factory=dict)
