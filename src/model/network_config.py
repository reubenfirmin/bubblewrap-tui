"""Network configuration model."""

from model.ui_field import ConfigBase, UIField


class NetworkConfig(ConfigBase):
    """Network settings for the sandbox."""

    share_net = UIField(
        bool, False, "opt-net",
        "Allow network", "Enable host network access",
        bwrap_flag="--share-net",
    )
    bind_resolv_conf = UIField(
        bool, False, "opt-resolv-conf",
        "DNS config", "/etc/resolv.conf for hostname resolution",
        # bwrap_args handled specially - needs to iterate DNS paths
    )
    bind_ssl_certs = UIField(
        bool, False, "opt-ssl-certs",
        "SSL certificates", "/etc/ssl/certs for HTTPS",
        # bwrap_args handled specially - needs to iterate cert paths
    )
