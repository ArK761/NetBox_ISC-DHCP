import json

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt

from ..i18n import t
from . import audit, build
from .models import ExportFile


def _client_allowed(request):
    """Logged-in user with view right, or a client IP from PLUGINS_CONFIG allowed_client_ips (DHCP servers)."""
    if request.user.is_authenticated and request.user.has_perm("netbox_isc_dhcp.view_exportfile"):
        return True
    from .servers import allowed_ips

    ips = set(settings.PLUGINS_CONFIG.get("netbox_isc_dhcp", {}).get("allowed_client_ips", []) or []) | allowed_ips()
    return audit.client_ip(request) in ips


class ManifestView(View):
    def get(self, request):
        if not _client_allowed(request):
            raise PermissionDenied
        audit.download(request)
        return HttpResponse(json.dumps(build.manifest(), indent=1), content_type="application/json")


class FileView(View):
    def get(self, request, path):
        if not _client_allowed(request):
            raise PermissionDenied
        row = ExportFile.objects.filter(path="/" + path.lstrip("/")).first()
        if row is None:
            raise Http404
        audit.download(request, row.path)
        resp = HttpResponse(row.content, content_type="text/plain; charset=utf-8")
        resp["X-SHA256"] = row.sha256
        return resp


class ExportPageView(LoginRequiredMixin, View):
    """Admin view of what the DHCP server gets: directory tree of the stored files."""

    def get(self, request):
        if not request.user.has_perm("netbox_isc_dhcp.view_exportfile"):
            raise PermissionDenied
        m = build.manifest()
        rows = list(ExportFile.objects.order_by("path").only("pk", "path", "area", "sha256", "size", "updated"))
        tree = {}
        for r in rows:
            d, name = r.path.rsplit("/", 1)
            tree.setdefault(d or "/", []).append({"r": r, "name": name})
        dirs = [{"dir": d, "files": sorted(f, key=lambda x: build._net_key(x["r"].path) if x["r"].area == "subnet" else (0, 0, x["name"]))}
                for d, f in sorted(tree.items())]
        for d in dirs:
            d["size"] = sum(x["r"].size for x in d["files"])
        last = max((r.updated for r in rows), default=None)
        return render(request, "netbox_isc_dhcp/export/export.html", {
            "cfg_label": __import__("netbox_isc_dhcp.export.versions", fromlist=["x"]).label(build.manifest_hash(), create=True),
            "m": m, "dirs": dirs, "last": last, "total_size": sum(r.size for r in rows),
            "files_text": t("exp.files", n=m["count"]),
        })


class ExportRegenView(LoginRequiredMixin, View):
    def post(self, request):
        if not request.user.has_perm("netbox_isc_dhcp.change_exportfile") and not request.user.is_superuser:
            raise PermissionDenied
        build.regen_all(cause=t("aud.c_button"))
        messages.success(request, t("exp.regenerated"))
        return redirect("plugins:netbox_isc_dhcp:export")


class AuditView(LoginRequiredMixin, View):
    PER_PAGE = 100

    def get(self, request):
        from .models import AuditEvent

        if not request.user.has_perm("netbox_isc_dhcp.view_auditevent"):
            raise PermissionDenied
        kind = request.GET.get("kind", "")
        qs = AuditEvent.objects.all()
        if kind in ("regen", "download", "plan", "report", "agent", "admin"):
            qs = qs.filter(kind=kind)
        page = int(request.GET.get("p", "1")) if request.GET.get("p", "1").isdigit() else 1
        total = qs.count()
        events = list(qs[(page - 1) * self.PER_PAGE: page * self.PER_PAGE])
        from . import versions

        labels = versions.labels()
        for e in events:
            e.cfg_label = labels.get(e.manifest_hash, e.manifest_hash[:12])
            ch = e.changes or []
            e.n_add = sum(1 for c in ch if c.get("action") == "add")
            e.n_upd = sum(1 for c in ch if c.get("action") == "update")
            e.n_del = sum(1 for c in ch if c.get("action") == "delete")
            e.n_dl = sum(1 for c in ch if c.get("action") == "download")
        return render(request, "netbox_isc_dhcp/export/audit.html", {
            "events": events, "kind": kind, "page": page, "has_next": page * self.PER_PAGE < total, "total": total,
            "kinds": [("", t("aud.all")), ("regen", t("aud.regen")), ("download", t("aud.download")), ("plan", t("aud.plan_kind")), ("report", t("aud.report")),
                      ("agent", t("aud.agent_kind")), ("admin", t("aud.admin_kind"))],
        })


def _st():
    from ..models import PluginSettings, settings_obj

    return settings_obj() or PluginSettings.objects.create()


def _admin_audit(request, log):
    """Audit of changes to DHCP servers / agent settings: who, from where, old -> new."""
    from .models import AuditEvent

    AuditEvent.objects.create(time=timezone.now(), kind="admin", user=request.user.username, client_ip=audit.client_ip(request),
                              cause=t("aud.admin_servers"), changes=[{"path": k, "action": "update", "old": str(o), "new": str(n)} for k, o, n in log])


class ServersInlineView(LoginRequiredMixin, View):
    """Add / edit / switch / delete DHCP servers on the plugin settings page."""

    def post(self, request):
        from .models import DHCPServer
        from .servers import invalidate, valid_address

        if not request.user.has_perm("netbox_isc_dhcp.change_pluginsettings"):
            raise PermissionDenied
        action = request.POST.get("field", "")
        pk = request.POST.get("pk", "")
        srv = DHCPServer.objects.filter(pk=int(pk)).first() if pk.isdigit() else None
        name, addr = request.POST.get("name", "").strip()[:100], request.POST.get("address", "").strip()[:255]
        log = []
        if action in ("add", "edit"):
            if not name or not valid_address(addr):
                messages.error(request, t("srv.err"))
                return redirect("plugins:netbox_isc_dhcp:pluginsettings_list")
            if action == "add":
                last = DHCPServer.objects.order_by("-order").first()
                DHCPServer.objects.create(name=name, address=addr, order=(last.order + 1) if last else 1)
                log = [("add", "", f"{name} {addr}")]
            elif srv:
                log = [("edit", f"{srv.name} {srv.address}", f"{name} {addr}")]
                srv.name, srv.address = name, addr
                srv.save()
        elif action == "cmds":  # shared by all DHCP servers
            from ..base_config import is_safe_path

            bdir = request.POST.get("backup_dir", "").strip()[:255]
            if bdir and not is_safe_path(bdir):
                messages.error(request, t("srv.err_path"))
                return redirect(reverse("plugins:netbox_isc_dhcp:pluginsettings_list") + "#isc-servers")
            st = _st()
            before = (st.agent_test_cmd, st.agent_restart_cmd, st.agent_backup_dir)
            st.agent_test_cmd = request.POST.get("test_cmd", "").strip()[:255] or st.agent_test_cmd
            st.agent_restart_cmd = request.POST.get("restart_cmd", "").strip()[:255] or st.agent_restart_cmd
            st.agent_backup_dir = bdir
            st.save()
            log = [("test", before[0], st.agent_test_cmd), ("restart", before[1], st.agent_restart_cmd), ("backup", before[2], st.agent_backup_dir)]
            log = [x for x in log if x[1] != x[2]]
        elif action == "mode":
            st = _st()
            log = [("mode", st.agent_mode, "export" if request.POST.get("value") == "export" else "plan")]
            st.agent_mode = log[0][2]
            st.save()
        elif action == "staged":
            st = _st()
            log = [("staged_rollout", str(st.staged_rollout), str(request.POST.get("value") == "1"))]
            st.staged_rollout = request.POST.get("value") == "1"
            st.save()
        elif action == "interval":
            from .agent import INTERVALS

            st = _st()
            v = int(request.POST.get("value", "0")) if request.POST.get("value", "").isdigit() else 0
            if v in INTERVALS:
                log = [("interval", str(st.agent_interval), str(v))]
                st.agent_interval = v
                st.save()
        elif action == "first" and srv:  # only one server can be first; others keep their relative order
            from .agent import first_server, isc_mismatch

            cur = first_server()
            if isc_mismatch() and cur is not None and cur.pk != srv.pk:
                messages.error(request, t("srv.err_first_isc"))
                return redirect(reverse("plugins:netbox_isc_dhcp:pluginsettings_list") + "#isc-servers")
            rest = [x for x in DHCPServer.objects.order_by("pk") if x.pk != srv.pk]  # list order (pk) never changes
            for i, x in enumerate([srv] + rest, 1):
                if x.order != i:
                    x.order = i
                    x.save(update_fields=["order"])
            log = [("first", cur.name if cur else "", srv.name)]
        elif action == "release" and srv:  # admin lets the next servers go on without this server's OK for the current set
            from . import build

            srv.released_hash = build.manifest_hash()
            srv.save(update_fields=["released_hash"])
            log = [("release", "", srv.name)]
        elif action == "retry" and srv:  # the current set failed here; admin fixed the server -> send it again
            log = [("retry " + srv.name, srv.last_result, "")]
            srv.last_result = ""
            srv.save(update_fields=["last_result"])
        elif action == "toggle" and srv:
            from .agent import first_server, isc_mismatch

            cur = first_server()
            if srv.enabled and isc_mismatch() and cur is not None and cur.pk == srv.pk:
                messages.error(request, t("srv.err_first_isc"))
                return redirect(reverse("plugins:netbox_isc_dhcp:pluginsettings_list") + "#isc-servers")
            srv.enabled = not srv.enabled
            srv.save()
            log = [("enabled " + srv.name, str(not srv.enabled), str(srv.enabled))]
        elif action == "delete" and srv:
            log = [("delete", f"{srv.name} {srv.address}", "")]
            srv.delete()
        if log:
            _admin_audit(request, log)
        invalidate()
        messages.success(request, t("msg.saved"))
        return redirect(reverse("plugins:netbox_isc_dhcp:pluginsettings_list") + "#isc-servers")


def _json_body(request):
    try:
        return json.loads(request.body or b"{}")
    except ValueError:
        return None


def _refused_contact(request):
    """Audit an agent contact from an IP that is not a DHCP server (once per IP in 10 min) - shows why an agent does not appear."""
    from datetime import timedelta

    from .models import AuditEvent

    ip = audit.client_ip(request)
    if AuditEvent.objects.filter(kind="agent", client_ip=ip, result="refused", time__gte=timezone.now() - timedelta(minutes=10)).exists():
        return
    AuditEvent.objects.create(time=timezone.now(), kind="agent", client_ip=ip, result="refused", cause=t("aud.agent_refused", ip=ip),
                              output=f"REMOTE_ADDR={request.META.get('REMOTE_ADDR', '')} X-Forwarded-For={request.META.get('HTTP_X_FORWARDED_FOR', '')}")


def _wants_text(request):
    return request.GET.get("format") == "text" or "text/plain" in request.META.get("HTTP_ACCEPT", "")


def _agent_data(request):
    """Agent request data: form fields (bash agent) or JSON body."""
    if request.method == "POST" and request.content_type == "application/json":
        body = _json_body(request)
        return body if isinstance(body, dict) else None
    return request.POST if request.method == "POST" else request.GET


@method_decorator(csrf_exempt, name="dispatch")
class PlanView(View):
    """Agent contact. POST (form: files=<sha256sum output>, agent, isc, dhcpd, running | JSON {"files": {path: sha}})
    -> state + ordered steps. ?format=text = TAB separated lines for the bash agent. GET = plan for an empty server."""

    def _plan(self, request, have, data):
        from django.urls import reverse
        from urllib.parse import quote

        from . import versions
        from .agent import as_text, gate, heartbeat, make_plan, managed_dirs, server_for
        from .models import AuditEvent
        from ..models import CONF_DIR, base_path, settings_obj

        if not _client_allowed(request):
            _refused_contact(request)
            raise PermissionDenied
        server = server_for(request)
        if data and request.method == "POST":
            heartbeat(server, request, data)
        mh = build.manifest_hash()
        ver = versions.ensure(mh)
        st = settings_obj()
        mode = st.agent_mode if st else "plan"
        info = {"mode": mode, "hash": mh, "cfg": ver.label if ver else "", "server": server.name if server else "",
                "interval": st.agent_interval if st else 60, "conf_dir": CONF_DIR, "base": base_path(),
                "dir": managed_dirs()}  # the agent sends sha256 of every file in these dirs (+ dhcpd.conf) next time
        text = _wants_text(request)

        def reply(steps, extra=None, status=200):
            d = dict(info, **(extra or {}))
            if text:
                return HttpResponse(as_text(d, steps), status=status, content_type="text/plain; charset=utf-8")
            return HttpResponse(json.dumps(dict(d, steps=steps), indent=1), status=status, content_type="application/json")

        if not ExportFile.objects.filter(area="conf").exists():  # never let a server restart without a dhcpd.conf
            return reply([], {"error": "dhcpd.conf is not generated"}, status=409)
        reason, names = gate(server, mh)
        if reason:
            return reply([], {"wait": reason, "wait_for": ",".join(names)})
        if mode == "export" and server is not None and server.last_result == "ok" and server.last_hash == mh:
            steps = []  # export = everything, but only when the set changed since this server's last OK (no restart on every poll)
        else:
            steps = make_plan(have, server, lambda p: request.build_absolute_uri(reverse("plugins:netbox_isc_dhcp:export_file", kwargs={"path": quote(p.lstrip("/"))})),
                              request.build_absolute_uri(reverse("plugins:netbox_isc_dhcp:export_report")), mh, mode)
        if steps:
            AuditEvent.objects.create(time=timezone.now(), kind="plan", server=server.name if server else "", client_ip=audit.client_ip(request),
                                      user=request.user.username if request.user.is_authenticated else "", manifest_hash=mh,
                                      cause=t("aud.plan_" + mode, n=len(steps)) + (f" · {ver.label}" if ver else ""),
                                      changes=[{"path": x.get("path") or x.get("cmd") or ", ".join(x.get("paths", [])) or x.get("url", ""), "action": x["op"]} for x in steps])
        return reply(steps)

    def get(self, request):
        return self._plan(request, {}, None)

    def post(self, request):
        from .agent import parse_have

        data = _agent_data(request)
        if data is None:
            return HttpResponse('{"error": "body must be JSON {\\"files\\": {path: sha256}} or a form"}', status=400, content_type="application/json")
        files = data.get("files", {})
        if isinstance(files, dict):
            have = {str(k): str(v) for k, v in files.items()}
        else:
            have = parse_have(str(files or ""))
        return self._plan(request, have, data)


@method_decorator(csrf_exempt, name="dispatch")
class ReportView(View):
    """Agent result. POST form or JSON: hash, result ok|test_failed|rolled_back|failed, output, done."""

    RESULTS = ("ok", "test_failed", "rolled_back", "failed")

    def post(self, request):
        from . import versions
        from .agent import server_for
        from .models import AuditEvent

        if not _client_allowed(request):
            raise PermissionDenied
        body = _agent_data(request)
        if body is None or body.get("result") not in self.RESULTS:
            return HttpResponse('{"error": "result must be one of ok, test_failed, rolled_back, failed"}', status=400, content_type="application/json")
        server = server_for(request)
        now = timezone.now()
        h = str(body.get("hash", ""))[:64]
        done = body.get("done", [])
        done = done if isinstance(done, list) else [x for x in str(done).split() if x]
        AuditEvent.objects.create(time=now, kind="report", server=server.name if server else "", client_ip=audit.client_ip(request),
                                  manifest_hash=h, result=body["result"], output=str(body.get("output", ""))[:20000],
                                  cause=t("aud.result_" + body["result"]) + (f" · {versions.label(h)}" if h else ""),
                                  changes=[{"path": str(x), "action": "done"} for x in done][:2000])
        if server:
            server.last_hash, server.last_result, server.last_report = h, body["result"], now
            fields = ["last_hash", "last_result", "last_report"]
            run = str(body.get("running", "") or (h if body["result"] == "ok" else ""))[:64]
            if run:
                server.running_hash = run
                fields.append("running_hash")
            server.save(update_fields=fields)
        return HttpResponse('{"ok": true}', content_type="application/json")
