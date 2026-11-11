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


_NOTICE = ('<div class="alert text-bg-{level} border-0 d-flex align-items-center gap-2 py-2 mb-2 fw-semibold"><i class="mdi {icon} fs-4"></i>'
           '<span>{text}</span>{link}</div>')


def inject_badge(response, notices=()):
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
    for level, icon, text, url, link_text in notices:  # plugin warnings at the top of the page (never cover buttons)
        link = f' <a class="ms-auto fw-bold text-reset" href="{escape(url)}">{escape(link_text)} &rarr;</a>' if url else ""
        badge += _NOTICE.format(level=level, icon=icon, text=escape(text), link=link)
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


def _error_once(request, text, level=messages.ERROR):
    """Add a message unless the same text is already waiting (e.g. after a redirect)."""
    storage = messages.get_messages(request)
    waiting = [str(m.message) for m in getattr(storage, "_queued_messages", [])]
    try:
        waiting += [str(m.message) for m in storage._loaded_messages]
    except Exception:
        pass
    if text not in waiting:
        messages.add_message(request, level, text)


class DNSWarningMiddleware:
    """On plugin pages: version badge and the plugin warnings (no DNS, incompatible subnets, individual subnets) at the top."""

    def __init__(self, get_response):
        self.get_response = get_response

    def _notices(self, request):
        from django.urls import reverse

        from .compat import incompatible
        from .models import DNSServer, SubnetOverride

        out = []
        if not DNSServer.objects.filter(active=True).exists():
            out.append(("danger", "mdi-dns-outline", t("warn.no_dns"), reverse("plugins:netbox_isc_dhcp:dnsserver_list"), t("menu.dns")))
        subnets = reverse("plugins:netbox_isc_dhcp:subnetconfig_list")
        bad = incompatible()
        if bad:
            out.append(("danger", "mdi-alert-octagon-outline", t("warn.incompat", n=len(bad)), subnets, t("menu.subnets")))
        n = SubnetOverride.objects.count()
        if n:
            out.append(("warning", "mdi-pencil-outline", t("warn.overrides", n=n), subnets, t("menu.subnets")))
        return out

    def __call__(self, request):
        on_plugin = request.method == "GET" and PLUGIN_PATH in request.path
        notices = []
        if on_plugin and request.user.is_authenticated:
            try:
                notices = self._notices(request)
            except Exception:
                notices = []
        response = self.get_response(request)
        if on_plugin:
            try:
                response = inject_badge(response, notices)
            except Exception:
                pass
        return response
