try:
    from netbox.plugins import PluginConfig
except ImportError:  # allows importing pure modules (pools.py) outside NetBox, e.g. in tests
    PluginConfig = object


class ISCDHCPConfig(PluginConfig):
    name = "netbox_isc_dhcp"
    verbose_name = "ISC DHCP"
    description = "Generate ISC DHCP configuration from NetBox data"
    version = "0.1.0"
    author = "ArK761"
    base_url = "isc-dhcp"
    min_version = "4.0.0"
    default_settings = {
        # IPs allowed to read the generated files without a password (used in a later step)
        "allowed_client_ips": [],
    }


config = ISCDHCPConfig
