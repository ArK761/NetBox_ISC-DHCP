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


_TREE_CSS = (
    "<style>details.isc-notice{display:block!important}details.isc-notice>summary{list-style:none;cursor:pointer}details.isc-notice>summary::-webkit-details-marker{display:none}"
    "details.isc-notice .isc-hide,details.isc-notice[open] .isc-show{display:none}details.isc-notice[open] .isc-hide{display:inline}"
    "details.isc-notice .isc-tog{border:1px solid currentColor;border-radius:.3rem;padding:0 .5rem}details.isc-notice .isc-tree{margin:.4rem 0 .1rem 2rem;max-height:22rem;overflow:auto}"
    "details.isc-notice .isc-tree ul{list-style:none;padding-left:1.2rem;margin:.1rem 0 .4rem;border-left:1px solid currentColor}"
    "details.isc-notice a{color:inherit}details.isc-notice .isc-tree li{margin:.1rem 0}</style>"
)
_NOTICE = ('<div class="alert text-bg-{level} border-0 d-flex align-items-center gap-2 py-2 mb-2 fw-semibold"><i class="mdi {icon} fs-4"></i>'
           '<span>{text}</span>{link}</div>')


def inject_badge(response, notices=(), toggle=("Show tree", "Hide tree")):
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
    if notices:
        badge += _TREE_CSS
    for level, icon, text, url, link_text, *rest in notices:  # plugin warnings at the top of the page (never cover buttons)
        tree = rest[0] if rest else None
        link = "" if tree else f' <a class="ms-auto fw-bold text-reset" href="{escape(url)}">{escape(link_text)} &rarr;</a>' if url else ""
        if not tree:
            badge += _NOTICE.format(level=level, icon=icon, text=escape(text), link=link)
            continue
        # tree: pool -> its subnets; every item opens in a new window
        nodes = ""
        for (pool, pool_url), items in tree.items():
            leaves = "".join(
                f'<li><a href="{escape(u)}" target="_blank" rel="noopener"><code class="text-reset">{escape(lbl)}</code></a>'
                + (f' <span class="opacity-75">– {escape(note)}</span>' if note else "") + "</li>"
                for lbl, u, note in items[:200])
            more = f"<li>… +{len(items) - 200}</li>" if len(items) > 200 else ""
            nodes += (f'<li><a href="{escape(pool_url)}" target="_blank" rel="noopener"><i class="mdi mdi-folder-outline"></i> <b>{escape(pool)}</b></a>'
                      f' <span class="opacity-75">({len(items)})</span><ul>{leaves}{more}</ul></li>')
        badge += (f'<details class="isc-notice alert text-bg-{level} border-0 py-2 mb-2 fw-semibold">'
                  f'<summary class="d-flex align-items-center gap-2"><i class="mdi {icon} fs-4"></i><span>{escape(text)}</span>'
                  f'<span class="isc-tog ms-auto text-nowrap"><i class="mdi mdi-file-tree"></i> '
                  f'<span class="isc-show">{escape(toggle[0])} &#9662;</span><span class="isc-hide">{escape(toggle[1])} &#9652;</span></span></summary>'
                  f'<div class="isc-tree fw-normal"><ul class="border-0 ps-0">{nodes}</ul></div></details>')
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
        from .models import ConfigVariable
        from .services import variable_usage

        missing = sorted(set(variable_usage()) - set(ConfigVariable.objects.values_list("name", flat=True)))
        if missing:
            out.append(("danger", "mdi-variable", t("warn.var_unknown", n=len(missing), names=", ".join(missing[:5])),
                        reverse("plugins:netbox_isc_dhcp:variables"), t("menu.vars")))
        subnets = reverse("plugins:netbox_isc_dhcp:subnetconfig_list")
        from .i18n import tmsg

        bad = incompatible()
        if bad:
            tree = {}
            for x in bad:
                pool_url = reverse("plugins:netbox_isc_dhcp:pooltemplate", kwargs={"pk": x["pool_pk"]})
                tree.setdefault((x["pool"], pool_url), []).append((x["prefix"], f"{pool_url}?p={x.get('prefix_pk', '')}", tmsg(x["reason"])))
            out.append(("danger", "mdi-alert-octagon-outline", t("warn.incompat", n=len(bad)), subnets, t("menu.subnets"), tree))
        ovr = list(SubnetOverride.objects.select_related("pool"))
        if ovr:
            tree = {}
            for o in ovr:
                pool_url = reverse("plugins:netbox_isc_dhcp:pooltemplate", kwargs={"pk": o.pool_id})
                url = reverse("plugins:netbox_isc_dhcp:subnet_override", kwargs={"pk": o.pool_id, "prefix_pk": o.prefix_id})
                tree.setdefault((o.pool.name, pool_url), []).append((o.prefix_text, url, ""))
            out.append(("warning", "mdi-pencil-outline", t("warn.overrides", n=len(ovr)), subnets, t("menu.subnets"), tree))
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
                response = inject_badge(response, notices, (t("lbl.tree_show"), t("lbl.tree_hide")))
            except Exception:
                pass
        return response
