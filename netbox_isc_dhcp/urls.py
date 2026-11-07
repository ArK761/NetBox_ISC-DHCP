from django.urls import include, path
from utilities.urls import get_model_urls

from . import views  # noqa: F401  (registers the views)

app = "netbox_isc_dhcp"

urlpatterns = []
for prefix, model in (("base-config", "baseconfig"), ("groups", "dhcpgroup"), ("dns", "dnsserver"), ("settings", "pluginsettings")):
    urlpatterns += [
        path(f"{prefix}/", include(get_model_urls(app, model, detail=False))),
        path(f"{prefix}/<int:pk>/", include(get_model_urls(app, model))),
    ]
