import json

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views import View

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
        if kind in ("regen", "download", "report"):
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
            "kinds": [("", t("aud.all")), ("regen", t("aud.regen")), ("download", t("aud.download")), ("report", t("aud.report"))],
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
                DHCPServer.objects.create(name=name, address=addr)
            elif srv:
                srv.name, srv.address = name, addr
                srv.save()
        elif action == "toggle" and srv:
            srv.enabled = not srv.enabled
            srv.save()
        elif action == "delete" and srv:
            srv.delete()
        invalidate()
        messages.success(request, t("msg.saved"))
        return redirect(reverse("plugins:netbox_isc_dhcp:pluginsettings_list") + "#isc-servers")
