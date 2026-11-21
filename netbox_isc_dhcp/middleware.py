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
_BADGE = ('<div id="isc-dhcp-version" class="text-end mb-2"><a href="%s" target="_blank" class="me-2 small fw-semibold">'
          '<i class="mdi mdi-file-pdf-box"></i> %s</a>' + _PILL + "</div>")
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


def notices_html(notices, toggle=("Show tree", "Hide tree")):
    """HTML of the plugin warning bars (also served live by the notices view)."""
    badge = ""
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
    return badge


_LIVE_JS = (
    "<script>(function(){var b=document.getElementById('isc-notices');if(!b||!window.fetch)return;"
    "function go(){if(document.hidden)return;fetch(b.dataset.url,{credentials:'same-origin'}).then(function(r){return r.status==200?r.text():null}).then(function(h){"
    "if(h===null||h===b.innerHTML)return;var o=[].map.call(b.querySelectorAll('details[open] summary'),function(x){return x.textContent});"
    "b.innerHTML=h;[].forEach.call(b.querySelectorAll('details summary'),function(x){if(o.indexOf(x.textContent)>-1)x.parentNode.open=true})}).catch(function(){})}"
    "setInterval(go,10000);document.addEventListener('visibilitychange',go)})();</script>"
)


def _live_box(notices, toggle):
    """Warning bars in a box that refreshes itself every 10 s (state of servers changes without a page reload)."""
    from django.urls import reverse

    try:
        url = reverse("plugins:netbox_isc_dhcp:notices")
    except Exception:
        return notices_html(notices, toggle)
    return f'<div id="isc-notices" data-url="{escape(url)}">{notices_html(notices, toggle)}</div>' + _LIVE_JS


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
    from django.urls import reverse

    from .i18n import t

    try:
        manual = reverse("plugins:netbox_isc_dhcp:manual")
    except Exception:
        manual = "/plugins/isc-dhcp/manual/"
    badge = _BADGE % (manual, escape(t("lbl.manual")), escape(label()))
    badge += _TREE_CSS + _live_box(notices, toggle)
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
        out += self._server_notices()
        return out

    @staticmethod
    def _server_notices():
        """DHCP servers: different ISC versions, ISC missing, CFG mismatch, silent agent, dhcpd down."""
        from django.urls import reverse

        from .export import build, versions
        from .export.agent import enabled_servers, isc_versions, stale
        from .models import settings_obj

        url = reverse("plugins:netbox_isc_dhcp:pluginsettings_list") + "#isc-servers"
        label = t("srv.title")
        srvs = enabled_servers()
        if not srvs:
            return []
        out = []
        iv = isc_versions()
        if len(iv) > 1:
            out.append(("danger", "mdi-alert-octagon-outline", t("warn.isc_mismatch", list="; ".join(f"{v}: {', '.join(n)}" for v, n in iv.items())), url, label))
        missing = [s.name for s in srvs if s.isc_version == "none"]
        if missing:
            out.append(("danger", "mdi-alert-octagon-outline", t("warn.isc_missing", names=", ".join(missing)), url, label))
        mh = build.manifest_hash()
        lab = versions.labels()
        bad = [f"{s.name} {lab.get(s.running_hash, s.running_hash[:12])}" for s in srvs if s.last_seen and s.running_hash and s.running_hash != mh]
        if bad:
            out.append(("warning", "mdi-file-compare", t("warn.cfg_mismatch", list=", ".join(bad), cur=lab.get(mh, mh[:12])), url, label))
        st = settings_obj()
        silent = [s.name for s in srvs if s.last_seen and stale(s, st.agent_interval if st else 60)]
        if silent:
            out.append(("danger", "mdi-lan-disconnect", t("warn.agent_stale", names=", ".join(silent)), url, label))
        plain = [s.name for s in srvs if s.last_seen and s.agent_insecure]
        if plain:
            out.append(("warning", "mdi-lock-open-alert-outline", t("warn.insecure", names=", ".join(plain)), url, label))
        def _admin_off(s):  # stopped from NetBox (button or test server after its check): not a fault
            return s.dhcpd_by == "admin" and s.dhcpd_running is False

        svcbad = [f"{s.name} ({s.svc_state})" for s in srvs if s.last_seen and s.svc_state not in ("", "active", "none") and not _admin_off(s)]
        if svcbad:
            out.append(("warning", "mdi-cog-off-outline", t("warn.svc_bad", names=", ".join(svcbad)), url, label))
        svcoff = [f"{s.name} ({s.svc_state})" for s in srvs if s.last_seen and s.svc_state not in ("", "active", "none") and _admin_off(s)]
        if svcoff:
            out.append(("info", "mdi-information-outline", t("warn.svc_admin_off", names=", ".join(svcoff)), url, label))
        foreign = [s.name for s in srvs if s.takeover == "foreign"]
        if foreign:
            out.append(("warning", "mdi-server-security", t("warn.takeover", names=", ".join(foreign)), url, label))
        from datetime import timedelta as _td

        from django.utils import timezone as _tz

        from .export.models import AuditEvent as _AE

        hour = _tz.now() - _td(hours=1)
        from django.db.models import Q as _Q

        from .i18n import TR as _TR

        _pre = _Q()
        for _txt in _TR["aud.cfg_manual"]:  # rows written in SK or EN (the language may have changed since)
            _pre |= _Q(cause__startswith=_txt.split("{")[0][:20])
        clash = [s.name for s in srvs if _AE.objects.filter(_pre, kind="agent", server=s.name, result="manual", time__gte=hour).count() >= 3]
        if clash:
            out.append(("danger", "mdi-sword-cross", t("warn.clash", names=", ".join(clash)), url, label))
        from .export.agent import disk_level as _dl, disk_rows as _dr

        for _lv, _cls, _key in (("warn", "danger", "warn.disk_crit"), ("info", "warning", "warn.disk_full")):
            _hit = [f"{s.name} ({', '.join(f'{m} {p} %' for m, p, l in _dr(s.disk_usage) if l == _lv)})" for s in srvs if _dl(s.disk_usage) == _lv]
            if _hit:
                out.append((_cls, "mdi-harddisk", t(_key, names="; ".join(_hit)), url, label))
        broken = [s.name for s in srvs if s.disk_broken]
        if broken:
            out.append(("danger", "mdi-alert-octagon-outline", t("warn.disk_broken", names=", ".join(broken)), url, label))
        down = [s.name for s in srvs if s.dhcpd_running is False and s.isc_version != "none" and s.dhcpd_by != "admin"]
        if down:
            out.append(("danger", "mdi-server-off", t("warn.dhcpd_down", names=", ".join(down)), url, label))
        return out

    def __call__(self, request):
        on_plugin = request.method == "GET" and PLUGIN_PATH in request.path and not request.path.endswith("/notices/")
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
