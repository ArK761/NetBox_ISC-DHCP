from django.urls import include, path
from utilities.urls import get_model_urls

from . import views  # noqa: F401  (registers the views)

app = "netbox_isc_dhcp"

urlpatterns = [
    path("dhcp/", views.DHCPHubView.as_view(), name="dhcp_hub"),
    path("dhcp/hosts/", include("netbox_isc_dhcp.hosts.urls")),
    path("dhcp/variables/", views.VariablesView.as_view(), name="variables"),
    path("dhcp/variables/inline/", views.VariablesInlineView.as_view(), name="variables_inline"),
    path("dhcp/variables/json/", views.VariablesJSONView.as_view(), name="variables_json"),
    path("settings/<int:pk>/inline/", views.PluginSettingsInlineView.as_view(), name="pluginsettings_inline"),
    path("dhcp/subnets/pools/<int:pk>/override/<int:prefix_pk>/", views.SubnetOverrideView.as_view(), name="subnet_override"),
    path("dhcp/subnets/pools/<int:pk>/inline/", views.PoolTemplateInlineView.as_view(), name="pooltemplate_inline"),
    path("dhcp/subnets/<int:pk>/inline/", views.SubnetConfigInlineView.as_view(), name="subnetconfig_inline"),
    path("dhcp/base-config/<int:pk>/inline/", views.BaseConfigInlineView.as_view(), name="baseconfig_inline"),
    path("settings/paths/inline/", views.DHCPPathInlineView.as_view(), name="dhcppath_inline_add"),
    path("settings/paths/<int:pk>/inline/", views.DHCPPathInlineView.as_view(), name="dhcppath_inline"),
]
for prefix, model in (("settings/paths", "dhcppath"), ("dhcp/groups/files", "dhcpfile"), ("dhcp/base-config", "baseconfig"), ("dhcp/subnets/pools", "pooltemplate"), ("dhcp/subnets", "subnetconfig"), ("dhcp/groups", "dhcpgroup"), ("dhcp/dns", "dnsserver"), ("settings", "pluginsettings")):
    urlpatterns += [
        path(f"{prefix}/", include(get_model_urls(app, model, detail=False))),
        path(f"{prefix}/<int:pk>/", include(get_model_urls(app, model))),
    ]
