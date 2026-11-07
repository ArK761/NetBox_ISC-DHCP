from django.contrib import messages

from .i18n import t

PLUGIN_PATH = "/plugins/isc-dhcp/"


class DNSWarningMiddleware:
    """Show an error on every plugin page while no DNS server is in use."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.method == "GET" and PLUGIN_PATH in request.path and request.user.is_authenticated:
            try:
                from .models import DNSServer

                if not DNSServer.objects.filter(active=True).exists():
                    messages.error(request, t("warn.no_dns"))
            except Exception:
                pass
        return self.get_response(request)
