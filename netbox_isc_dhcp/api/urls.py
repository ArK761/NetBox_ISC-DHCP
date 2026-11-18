from netbox.api.routers import NetBoxRouter

from . import views

app_name = "netbox_isc_dhcp-api"
router = NetBoxRouter()
router.register("baseconfig", views.BaseConfigViewSet)
router.register("dhcppath", views.DHCPPathViewSet)
router.register("dhcpgroup", views.DHCPGroupViewSet)
router.register("dhcpfile", views.DHCPFileViewSet)
router.register("dnsserver", views.DNSServerViewSet)
router.register("pluginsettings", views.PluginSettingsViewSet)
router.register("subnetconfig", views.SubnetConfigViewSet)
router.register("pooltemplate", views.PoolTemplateViewSet)
router.register("configvariable", views.ConfigVariableViewSet)
router.register("subnetoverride", views.SubnetOverrideViewSet)
from django.urls import path

from ..export import views as export_views

# agent API (key in "Authorization: Token <key>" from CFG pluginu -> DHCP servery + DHCP server IP); also readable in the browser when logged in
urlpatterns = router.urls + [
    path("agent/", export_views.PlanView.as_view(), name="agent_plan"),
    path("agent/report/", export_views.ReportView.as_view(), name="agent_report"),
    path("agent/bundle/", export_views.BundleView.as_view(), name="agent_bundle"),
    path("agent/self/", export_views.AgentSelfView.as_view(), name="agent_self"),
    path("agent/manifest.json", export_views.ManifestView.as_view(), name="agent_manifest"),
    path("agent/file/<path:path>", export_views.FileView.as_view(), name="agent_file"),
]
