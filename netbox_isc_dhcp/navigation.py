from netbox.plugins import PluginMenu, PluginMenuButton, PluginMenuItem

from .i18n import t_lazy


def _list_item(model, key):
    return PluginMenuItem(
        link=f"plugins:netbox_isc_dhcp:{model}_list",
        link_text=t_lazy(key),
        permissions=[f"netbox_isc_dhcp.view_{model}"],
        buttons=(
            PluginMenuButton(
                link=f"plugins:netbox_isc_dhcp:{model}_add",
                title="Add",
                icon_class="mdi mdi-plus-thick",
                permissions=[f"netbox_isc_dhcp.add_{model}"],
            ),
        ),
    )


def _open_item(model, key):
    """Singleton: the list URL redirects to the single object."""
    return PluginMenuItem(
        link=f"plugins:netbox_isc_dhcp:{model}_list",
        link_text=t_lazy(key),
        permissions=[f"netbox_isc_dhcp.view_{model}"],
    )


menu = PluginMenu(
    label="ISC DHCP",
    groups=(
        (
            "DHCP",
            (
                _open_item("baseconfig", "menu.base"),
                _list_item("dhcpgroup", "menu.groups"),
                _list_item("dnsserver", "menu.dns"),
                _open_item("pluginsettings", "menu.settings"),
            ),
        ),
    ),
    icon_class="mdi mdi-lan",
)
