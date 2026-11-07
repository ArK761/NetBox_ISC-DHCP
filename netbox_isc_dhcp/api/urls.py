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
urlpatterns = router.urls
