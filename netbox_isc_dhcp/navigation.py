from netbox.plugins import PluginMenu, PluginMenuButton, PluginMenuItem


def _item(model, label):
    return PluginMenuItem(
        link=f"plugins:netbox_isc_dhcp:{model}_list",
        link_text=label,
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


menu = PluginMenu(
    label="ISC DHCP",
    groups=(
        ("Config", (_item("baseconfig", "dhcpd.conf"), _item("dhcpgroup", "Groups"), _item("dnsserver", "DNS"))),
    ),
    icon_class="mdi mdi-lan",
)
