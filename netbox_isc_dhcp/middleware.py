from django.contrib import messages
from django.utils.html import escape

from .i18n import t
from .version import label

PLUGIN_PATH = "/plugins/isc-dhcp/"

_PILL = (
    '<span style="display:inline-block;padding:2px 10px;border-radius:999px;font-size:12px;'
    'font-weight:600;background:rgba(108,117,125,.9);color:#fff;">'
    '<i class="mdi mdi-tag-outline me-1"></i>%s</span>'
)
# Right-aligned, in the normal page flow (overlaps nothing), above the page messages.
_BADGE = '<div id="isc-dhcp-version" class="text-end mb-2">' + _PILL + "</div>"
_MARKER = '<div class="container-fluid tab-content py-3">'


def inject_badge(response):
    """Insert the version badge before </body> of an HTML response (no JavaScript involved)."""
    if response.status_code != 200 or getattr(response, "streaming", False):
        return response
    if "text/html" not in response.get("Content-Type", ""):
        return response
    charset = getattr(response, "charset", None) or "utf-8"
    body = response.content.decode(charset)
    if 'id="isc-dhcp-version"' in body:
        return response
    badge = _BADGE % escape(label())
    i = body.find(_MARKER)
    if i != -1:
        i += len(_MARKER)
    else:  # unknown layout: fall back to the end of the page
        i = body.rfind("</body>")
        if i == -1:
            return response
    response.content = (body[:i] + badge + body[i:]).encode(charset)
    if response.has_header("Content-Length"):
        response["Content-Length"] = str(len(response.content))
    return response


def _error_once(request, text):
    """Add an error message unless the same text is already waiting (e.g. after a redirect)."""
    storage = messages.get_messages(request)
    waiting = [str(m.message) for m in getattr(storage, "_queued_messages", [])]
    try:
        waiting += [str(m.message) for m in storage._loaded_messages]
    except Exception:
        pass
    if text not in waiting:
        messages.error(request, text)


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
                    _error_once(request, t("warn.no_dns"))
                from .compat import incompatible

                bad = incompatible()
                if bad:
                    _error_once(request, t("warn.incompat", n=len(bad)))
            except Exception:
                pass
        response = self.get_response(request)
        if on_plugin:
            try:
                response = inject_badge(response)
            except Exception:
                pass
        return response
