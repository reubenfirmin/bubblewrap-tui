"""UIField definitions for Network group."""

from model.ui_field import UIField


def _named(name: str, field: UIField) -> UIField:
    """Set the name attribute on a UIField and return it."""
    field.name = name
    return field


share_net = _named("share_net", UIField(
    bool, False, "opt-net",
    "Allow network", "Enable host network access",
    bwrap_flag="--share-net",
))

bind_resolv_conf = _named("bind_resolv_conf", UIField(
    bool, False, "opt-resolv-conf",
    "DNS config", "/etc/resolv.conf for hostname resolution",
    # bwrap_args handled by group's custom to_args
))

bind_ssl_certs = _named("bind_ssl_certs", UIField(
    bool, False, "opt-ssl-certs",
    "SSL certificates", "/etc/ssl/certs for HTTPS",
    # bwrap_args handled by group's custom to_args
))
