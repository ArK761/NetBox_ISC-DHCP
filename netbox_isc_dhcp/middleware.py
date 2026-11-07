from django.contrib import messages
from django.utils.html import escape

from .i18n import t
from .version import label

PLUGIN_PATH = "/plugins/isc-dhcp/"

_BADGE = (
    '<div id="isc-dhcp-version" style="position:fixed;left:12px;bottom:12px;z-index:2000;'
    "padding:2px 10px;border-radius:999px;font-size:12px;background:rgba(108,117,125,.9);"
    'color:#fff;pointer-events:none;"><i class="mdi mdi-tag-outline me-1"></i>%s</div>'
)


def inject_badge(response):
    """Insert the version badge before </body> of an HTML response (no JavaScript involved)."""
    if response.status_code != 200 or getattr(response, "streaming", False):
        return response
    if "text/html" not in response.get("Content-Type", ""):
        return response
    charset = getattr(response, "charset", None) or "utf-8"
    body = response.content.decode(charset)
    i = body.rfind("</body>")
    if i == -1 or 'id="isc-dhcp-version"' in body:
        return response
    response.content = (body[:i] + _BADGE % escape(label()) + body[i:]).encode(charset)
    if response.has_header("Content-Length"):
        response["Content-Length"] = str(len(response.content))
    return response


class DNSWarningMiddleware:
    """On plugin pages: error while no DNS server is in use, and the version badge."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        on_plugin = request.method == "GET" and PLUGIN_PATH in request.path
        if on_plugin and request.user.is_authenticated:
            try:
                from .models import DNSServer

                if not DNSServer.objects.filter(active=True).exists():
                    messages.error(request, t("warn.no_dns"))
            except Exception:
                pass
        response = self.get_response(request)
        if on_plugin:
            try:
                response = inject_badge(response)
            except Exception:
                pass
        return response
