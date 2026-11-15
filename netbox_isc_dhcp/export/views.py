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
        if kind in ("regen", "download", "plan", "report"):
            qs = qs.filter(kind=kind)
        page = int(request.GET.get("p", "1")) if request.GET.get("p", "1").isdigit() else 1
        total = qs.count()
        events = list(qs[(page - 1) * self.PER_PAGE: page * self.PER_PAGE])
        for e in events:
            ch = e.changes or []
            e.n_add = sum(1 for c in ch if c.get("action") == "add")
            e.n_upd = sum(1 for c in ch if c.get("action") == "update")
            e.n_del = sum(1 for c in ch if c.get("action") == "delete")
            e.n_dl = sum(1 for c in ch if c.get("action") == "download")
        return render(request, "netbox_isc_dhcp/export/audit.html", {
            "events": events, "kind": kind, "page": page, "has_next": page * self.PER_PAGE < total, "total": total,
            "kinds": [("", t("aud.all")), ("regen", t("aud.regen")), ("download", t("aud.download")), ("plan", t("aud.plan_kind")), ("report", t("aud.report"))],
        })


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
        if action in ("add", "edit"):
            if not name or not valid_address(addr):
                messages.error(request, t("srv.err"))
                return redirect("plugins:netbox_isc_dhcp:pluginsettings_list")
            if action == "add":
                last = DHCPServer.objects.order_by("-order").first()
                DHCPServer.objects.create(name=name, address=addr, order=(last.order + 1) if last else 1)
            elif srv:
                srv.name, srv.address = name, addr
                srv.save()
        elif action == "cmds" and srv:
            srv.test_cmd = request.POST.get("test_cmd", "").strip()[:255] or srv.test_cmd
            srv.restart_cmd = request.POST.get("restart_cmd", "").strip()[:255] or srv.restart_cmd
            srv.backup_dir = request.POST.get("backup_dir", "").strip()[:255]
            o = request.POST.get("order", "")
            srv.order = int(o) if o.isdigit() and 0 < int(o) < 100 else srv.order
            srv.save()
        elif action == "mode":
            from ..models import PluginSettings, settings_obj

            st = settings_obj() or PluginSettings.objects.create()
            st.agent_mode = "export" if request.POST.get("value") == "export" else "plan"
            st.save()
        elif action == "staged":
            from ..models import PluginSettings, settings_obj

            st = settings_obj() or PluginSettings.objects.create()
            st.staged_rollout = request.POST.get("value") == "1"
            st.save()
        elif action == "toggle" and srv:
            srv.enabled = not srv.enabled
            srv.save()
        elif action == "delete" and srv:
            srv.delete()
        invalidate()
        messages.success(request, t("msg.saved"))
        return redirect(reverse("plugins:netbox_isc_dhcp:pluginsettings_list") + "#isc-servers")


def _json_body(request):
    try:
        return json.loads(request.body or b"{}")
    except ValueError:
        return None


@method_decorator(csrf_exempt, name="dispatch")
class PlanView(View):
    """Agent: POST {"files": {path: sha256}} (what it has) -> ordered steps. GET = plan for an empty server."""

    def _plan(self, request, have):
        from django.urls import reverse
        from urllib.parse import quote

        from .agent import make_plan, server_for
        from .models import AuditEvent

        if not _client_allowed(request):
            raise PermissionDenied
        server = server_for(request)
        mh = build.manifest_hash()
        if not ExportFile.objects.filter(area="conf").exists():  # never let a server restart without a dhcpd.conf
            return HttpResponse(json.dumps({"error": "dhcpd.conf is not generated (plugin settings: dhcpd.conf path)", "steps": []}),
                                status=409, content_type="application/json")
        from ..models import settings_obj

        st = settings_obj()
        mode = st.agent_mode if st else "plan"
        from .agent import waiting_for

        wait = waiting_for(server, mh)
        if wait:  # staged rollout: earlier servers must report OK for this exact set first
            return HttpResponse(json.dumps({"mode": mode, "hash": mh, "server": server.name, "wait_for": wait, "steps": []}, indent=1),
                                content_type="application/json")
        if mode == "export" and server is not None and server.last_result == "ok" and server.last_hash == mh:
            steps = []  # export = everything, but only when the set changed since this server's last OK (no restart on every poll)
        else:
            steps = None
        steps = steps if steps is not None else make_plan(have, server, lambda p: request.build_absolute_uri(reverse("plugins:netbox_isc_dhcp:export_file", kwargs={"path": quote(p.lstrip("/"))})),
                          request.build_absolute_uri(reverse("plugins:netbox_isc_dhcp:export_report")), mh, mode)
        if steps:
            AuditEvent.objects.create(time=timezone.now(), kind="plan", server=server.name if server else "", client_ip=audit.client_ip(request),
                                      user=request.user.username if request.user.is_authenticated else "", manifest_hash=mh,
                                      cause=t("aud.plan_" + mode, n=len(steps)),
                                      changes=[{"path": x.get("path") or x.get("cmd") or ", ".join(x.get("paths", [])) or x.get("url", ""), "action": x["op"]} for x in steps])
        return HttpResponse(json.dumps({"mode": mode, "hash": mh, "server": server.name if server else None, "steps": steps}, indent=1), content_type="application/json")

    def get(self, request):
        return self._plan(request, {})

    def post(self, request):
        body = _json_body(request)
        if body is None or not isinstance(body.get("files", {}), dict):
            return HttpResponse('{"error": "body must be JSON {\\"files\\": {path: sha256}}"}', status=400, content_type="application/json")
        return self._plan(request, {str(k): str(v) for k, v in body.get("files", {}).items()})


@method_decorator(csrf_exempt, name="dispatch")
class ReportView(View):
    """Agent: POST {"hash", "result": ok|test_failed|rolled_back|failed, "output", "done": [step numbers]}."""

    RESULTS = ("ok", "test_failed", "rolled_back", "failed")

    def post(self, request):
        from .agent import server_for
        from .models import AuditEvent

        if not _client_allowed(request):
            raise PermissionDenied
        body = _json_body(request)
        if body is None or body.get("result") not in self.RESULTS:
            return HttpResponse('{"error": "result must be one of ok, test_failed, rolled_back, failed"}', status=400, content_type="application/json")
        server = server_for(request)
        now = timezone.now()
        AuditEvent.objects.create(time=now, kind="report", server=server.name if server else "", client_ip=audit.client_ip(request),
                                  manifest_hash=str(body.get("hash", ""))[:64], result=body["result"], output=str(body.get("output", ""))[:20000],
                                  cause=t("aud.result_" + body["result"]), changes=[{"path": str(x), "action": "done"} for x in body.get("done", [])][:2000])
        if server:
            server.last_hash, server.last_result, server.last_report = str(body.get("hash", ""))[:64], body["result"], now
            server.save(update_fields=["last_hash", "last_result", "last_report"])
        return HttpResponse('{"ok": true}', content_type="application/json")
