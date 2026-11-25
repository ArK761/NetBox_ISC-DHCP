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


_BAR_CSS = (
    "<style>"
    "body{padding-bottom:2.4rem}"
    "#isc-bar{position:fixed;left:0;right:0;bottom:0;z-index:1035;font-size:.8rem;font-weight:600}"
    "#isc-bar .isc-strip{display:flex;align-items:center;height:2rem;background:var(--tblr-bg-surface,var(--bs-body-bg,#fff));"
    "border-top:2px solid var(--tblr-warning,#f59f00);box-shadow:0 -.25rem .75rem rgba(0,0,0,.2)}"
    "#isc-bar .isc-view{flex:1;overflow:hidden;white-space:nowrap;position:relative;height:100%}"
    "#isc-bar .isc-track{position:absolute;top:0;height:100%;display:flex;align-items:center;gap:2.5rem;padding-left:100%;"
    "animation:iscrun var(--d,30s) linear infinite}"
    "#isc-bar .isc-view:hover .isc-track,#isc-bar .isc-tx.isc-mq:hover>span{animation-play-state:paused}"
    "@keyframes iscrun{from{transform:translateX(0)}to{transform:translateX(-100%)}}"
    "#isc-bar .isc-cnt{flex:none;display:flex;align-items:center;gap:.35rem;height:100%;padding:0 .9rem;cursor:pointer;user-select:none;"
    "border-left:1px solid rgba(128,128,128,.35)}"
    "#isc-bar .isc-arrow::before{content:'\\25B2'}#isc-notices.isc-open #isc-bar .isc-arrow::before{content:'\\25BC'}"
    "#isc-bar .isc-panel{display:none;max-height:60vh;overflow:auto}#isc-notices.isc-open #isc-bar .isc-panel{display:block}"
    "#isc-bar .isc-row{display:flex;align-items:center;gap:.5rem;height:1.9rem;padding:0 .9rem;white-space:nowrap;"
    "border-bottom:1px solid rgba(0,0,0,.25)}"
    "#isc-bar .isc-tx{flex:1;overflow:hidden;position:relative;height:100%}"
    "#isc-bar .isc-tx>span{position:absolute;top:0;line-height:1.9rem;white-space:nowrap}"
    "#isc-bar .isc-tx.isc-mq>span{animation:iscslide var(--d,12s) ease-in-out infinite alternate}"
    "@keyframes iscslide{0%,12%{transform:translateX(0)}88%,100%{transform:translateX(var(--s,0))}}"
    "#isc-bar a{color:inherit}#isc-bar code{background:transparent;color:inherit;padding:0}#isc-bar .isc-row a.isc-go{font-weight:700;text-decoration:underline}"
    "#isc-bar .isc-btn{border:1px solid currentColor;background:transparent;color:inherit;border-radius:.25rem;padding:0 .45rem;font-size:.72rem;line-height:1.3}"
    "#isc-bar .isc-tree{display:none;max-height:16rem;overflow:auto;padding:.3rem .9rem .5rem 2.4rem;font-weight:400}"
    "#isc-bar .isc-tree.isc-on{display:block}#isc-bar .isc-tree ul{list-style:none;padding-left:1.1rem;margin:.1rem 0 .3rem;border-left:1px solid currentColor}"
    "@media (prefers-reduced-motion:reduce){#isc-bar .isc-track{animation:none;padding-left:.8rem}#isc-bar .isc-tx.isc-mq>span{animation:none}}"
    "</style>"
)

_GROUP = {"danger": "danger", "warning": "warning"}  # everything else counts as info


def _count_text(n):
    from .i18n import current_language

    if current_language() == "sk":
        return f"{n} " + ("upozornenie" if n == 1 else "upozornenia" if 2 <= n <= 4 else "upozornení")
    return f"{n} " + ("warning" if n == 1 else "warnings")


def notices_html(notices, toggle=("Show tree", "Hide tree"), request=None):
    """The warnings bar at the bottom of plugin pages (also served live by the notices view): one line that scrolls,
    expandable to one line per warning (long text scrolls inside its line), trees and actions in the rows."""
    if not notices:
        return ""
    import hashlib

    token = ""
    if request is not None:
        from django.middleware.csrf import get_token

        token = get_token(request)
    rows, items, counts = "", "", {"danger": 0, "warning": 0, "info": 0}
    for level, icon, text, url, link_text, *rest in notices:
        tree = rest[0] if rest else None
        action = rest[1] if len(rest) > 1 else None
        counts[_GROUP.get(level, "info")] += 1
        items += f'<span class="badge text-bg-{level} isc-it"><i class="mdi {icon}"></i> {escape(text)}</span>'
        extra = ""
        tree_html = ""
        if tree:
            key = hashlib.sha1(text.encode()).hexdigest()[:10]
            nodes = ""
            for (pool, pool_url), its in tree.items():
                leaves = "".join(
                    f'<li><a href="{escape(u)}" target="_blank" rel="noopener"><code class="text-reset">{escape(lbl)}</code></a>'
                    + (f' <span class="opacity-75">– {escape(note)}</span>' if note else "") + "</li>"
                    for lbl, u, note in its[:200])
                more = f"<li>… +{len(its) - 200}</li>" if len(its) > 200 else ""
                nodes += (f'<li><a href="{escape(pool_url)}" target="_blank" rel="noopener"><i class="mdi mdi-folder-outline"></i> <b>{escape(pool)}</b></a>'
                          f' <span class="opacity-75">({len(its)})</span><ul>{leaves}{more}</ul></li>')
            extra += f'<button type="button" class="isc-btn isc-tree-btn" data-k="{key}"><i class="mdi mdi-file-tree"></i> {escape(toggle[0])}</button>'
            tree_html = f'<div class="isc-tree text-bg-{level}" data-k="{key}"><ul class="border-0 ps-0">{nodes}</ul></div>'
        if action and token:
            post, fields, label_ = action
            hidden = "".join(f'<input type="hidden" name="{escape(k)}" value="{escape(v)}">' for k, v in fields.items())
            extra += (f'<form method="post" action="{escape(post)}" class="m-0 isc-act"><input type="hidden" name="csrfmiddlewaretoken" value="{escape(token)}">'
                      f'{hidden}<input type="hidden" name="next" value=""><button class="isc-btn">{escape(label_)}</button></form>')
        if url:
            extra += f'<a class="isc-go" href="{escape(url)}">{escape(link_text)} &rarr;</a>'
        rows += (f'<div class="isc-row text-bg-{level}"><i class="mdi {icon} fs-5"></i><span class="isc-tx"><span>{escape(text)}</span></span>{extra}</div>'
                 + tree_html)
    dots = "".join(f'<span class="badge rounded-pill text-bg-{lv}">{n}</span>' for lv, n in counts.items() if n)
    return (f'<div id="isc-bar"><div class="isc-panel">{rows}</div><div class="isc-strip"><div class="isc-view"><div class="isc-track">{items}</div></div>'
            f'<div class="isc-cnt" role="button" tabindex="0">{dots} <span>{escape(_count_text(len(notices)))}</span> <span class="isc-arrow"></span></div></div></div>')


_LIVE_JS = (
    "<script>(function(){var b=document.getElementById('isc-notices');if(!b)return;var trees={};"
    "function marq(){var v=b.querySelector('.isc-view'),tr=b.querySelector('.isc-track');"
    "if(v&&tr)tr.style.setProperty('--d',Math.max(12,(tr.scrollWidth)/70)+'s');"
    "[].forEach.call(b.querySelectorAll('.isc-tx'),function(t){var i=t.firstElementChild;t.classList.remove('isc-mq');"
    "var o=i?i.scrollWidth-t.clientWidth:0;if(o>4){t.classList.add('isc-mq');t.style.setProperty('--s',(-o-16)+'px');t.style.setProperty('--d',Math.max(4,o/40)+'s')}})}"
    "function restore(){[].forEach.call(b.querySelectorAll('.isc-tree'),function(x){if(trees[x.dataset.k])x.classList.add('isc-on')})}"
    "b.addEventListener('click',function(e){var c=e.target.closest('.isc-cnt');if(c){b.classList.toggle('isc-open');setTimeout(marq,0);return}"
    "var t=e.target.closest('.isc-tree-btn');if(t){var k=t.dataset.k,x=b.querySelector('.isc-tree[data-k=\"'+k+'\"]');if(x){trees[k]=!x.classList.contains('isc-on');x.classList.toggle('isc-on')}}});"
    "b.addEventListener('keydown',function(e){if(e.target.closest('.isc-cnt')&&(e.key==='Enter'||e.key===' ')){e.preventDefault();b.classList.toggle('isc-open');setTimeout(marq,0)}});"
    "b.addEventListener('submit',function(e){var n=e.target.querySelector('input[name=next]');if(n)n.value=location.pathname+location.search});"
    "window.addEventListener('resize',marq);marq();"
    "if(!window.fetch)return;"
    "function go(){if(document.hidden)return;fetch(b.dataset.url,{credentials:'same-origin'}).then(function(r){return r.status==200?r.text():null}).then(function(h){"
    "if(h===null||h===b.innerHTML)return;b.innerHTML=h;restore();marq()}).catch(function(){})}"
    "setInterval(go,10000);document.addEventListener('visibilitychange',go)})();</script>"
)


def _live_box(notices, toggle, request=None, open_=False):
    """Warnings bar in a box that refreshes itself every 10 s (state of servers changes without a page reload)."""
    from django.urls import reverse

    try:
        url = reverse("plugins:netbox_isc_dhcp:notices")
    except Exception:
        return notices_html(notices, toggle, request)
    cls = ' class="isc-open"' if open_ else ""
    return f'<div id="isc-notices" data-url="{escape(url)}"{cls}>{notices_html(notices, toggle, request)}</div>' + _LIVE_JS


def inject_badge(response, notices=(), toggle=("Show tree", "Hide tree"), request=None, open_=False):
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
    badge += _BAR_CSS + _live_box(notices, toggle, request, open_)
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
        from .newvalues import notices as new_value_notices

        out += new_value_notices()
        rank = {"danger": 0, "warning": 1}
        return sorted(out, key=lambda n: rank.get(n[0], 2))  # red first, then yellow, then info

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
                from .models import settings_obj

                st = settings_obj()
                response = inject_badge(response, notices, (t("lbl.tree_show"), t("lbl.tree_hide")), request, bool(st and st.notices_open))
            except Exception:
                pass
        return response
