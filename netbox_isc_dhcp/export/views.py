from django.contrib.auth.decorators import login_not_required
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


def key_hash(key):
    import hashlib

    return hashlib.sha256(key.encode()).hexdigest()[:16] if key else ""


def _key_ok(request):
    """Agent key (Authorization: Token <key>). The new key always works; the previous one (or no key, '-') works too
    until every server switched. request._isc_key = "new" | "old" | ""."""
    import hmac

    from ..models import settings_obj

    st = settings_obj()
    key, old = ((st.agent_key, st.agent_key_old) if st else ("", "")) or ("", "")
    request._isc_key = ""
    if not key:
        return True
    parts = request.headers.get("Authorization", "").split(" ", 1)
    sent = parts[1].strip() if len(parts) == 2 and parts[0].lower() in ("token", "bearer") else ""
    if sent and hmac.compare_digest(sent, key):
        request._isc_key = "new"
        return True
    if old == "-" and not sent:
        request._isc_key = "old"
        return True
    if old and old != "-" and sent and hmac.compare_digest(sent, old):
        request._isc_key = "old"
        return True
    return False


def _key_progress(request, server, info):
    """Key change: hand the new key to an agent that still uses the old one; when every seen server uses the new one,
    the old key is deleted (audit)."""
    from ..models import settings_obj
    from .agent import enabled_servers
    from .models import AuditEvent

    st = settings_obj()
    if not st or not st.agent_key or server is None:
        return
    used = getattr(request, "_isc_key", "")
    if used == "old":
        info["key"] = st.agent_key  # the agent tests it and saves it
        return
    if used != "new":
        return
    h = key_hash(st.agent_key)
    if server.key_hash != h:
        server.key_hash = h
        server.save(update_fields=["key_hash"])
    if st.agent_key_old and all(s.key_hash == h for s in enabled_servers() if s.last_seen):
        type(st).objects.filter(pk=st.pk).update(agent_key_old="")
        AuditEvent.objects.create(time=timezone.now(), kind="admin", cause=t("aud.key_switched"),
                                  changes=[{"path": "agent_key_old", "action": "delete", "old": "***", "new": ""}])


def _client_allowed(request):
    """Logged-in user with view right, or a DHCP server: its IP is in the list AND it sends the agent key (when one exists)."""
    if request.user.is_authenticated and request.user.has_perm("netbox_isc_dhcp.view_exportfile"):
        return True
    from .servers import allowed_ips

    ips = set(settings.PLUGINS_CONFIG.get("netbox_isc_dhcp", {}).get("allowed_client_ips", []) or []) | allowed_ips()
    if audit.client_ip(request) not in ips:
        request._isc_refused = "ip"
        return False
    if not _key_ok(request):
        request._isc_refused = "key"
        return False
    return True


@method_decorator(login_not_required, name="dispatch")  # agent / DHCP servers: no login, access = client IP
class ManifestView(View):
    def get(self, request):
        if not _client_allowed(request):
            raise PermissionDenied
        audit.download(request)
        return HttpResponse(json.dumps(build.manifest(), indent=1), content_type="application/json")


@method_decorator(login_not_required, name="dispatch")  # agent / DHCP servers: no login, access = client IP
@method_decorator(csrf_exempt, name="dispatch")
class BundleView(View):
    """All requested files in one tar.gz (POST paths=<one path per line>) - the agent downloads a whole CFG in one request."""

    def post(self, request):
        import io
        import tarfile

        if not _client_allowed(request):
            _refused_contact(request)
            raise PermissionDenied
        data = _agent_data(request) or {}
        wanted = [p.strip() for p in str(data.get("paths", "")).splitlines() if p.strip()]
        rows = {r.path: r for r in ExportFile.objects.filter(path__in=wanted)}
        buf = io.BytesIO()
        now = timezone.now().timestamp()
        with tarfile.open(fileobj=buf, mode="w:gz", compresslevel=6) as tar:
            for p in wanted:
                r = rows.get(p)
                if r is None:
                    continue
                raw = (r.content or "").encode()
                info = tarfile.TarInfo(name=p.lstrip("/"))
                info.size, info.mode, info.mtime = len(raw), 0o644, now
                tar.addfile(info, io.BytesIO(raw))
        audit.download(request, f"bundle ({len(rows)} files)")
        resp = HttpResponse(buf.getvalue(), content_type="application/gzip")
        resp["X-Files"] = str(len(rows))
        return resp


@method_decorator(login_not_required, name="dispatch")  # agent / DHCP servers: no login, access = client IP
class AgentSelfView(View):
    """The agent script bundled with this plugin version (for the update pushed from NetBox)."""

    def get(self, request):
        from .agent import agent_script

        if not _client_allowed(request):
            _refused_contact(request)
            raise PermissionDenied
        ver, sha, raw = agent_script()
        if not raw:
            raise Http404
        resp = HttpResponse(raw, content_type="text/x-shellscript; charset=utf-8")
        resp["X-SHA256"], resp["X-Agent-Version"] = sha, ver
        return resp


@method_decorator(login_not_required, name="dispatch")  # agent / DHCP servers: no login, access = client IP
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
        from .models import DHCPServer as _S
        from .agent import stale as _stale, status_text as _status
        from ..models import settings_obj as _so
        from ..views import _ago

        _st = _so()
        agents = [{"s": x, "ago": _ago(x.last_seen) if x.last_seen else "", "stale": bool(x.last_seen) and _stale(x, _st.agent_interval if _st else 60),
                   "state": _status(x) if x.last_seen else ""} for x in _S.objects.order_by("pk")]
        return render(request, "netbox_isc_dhcp/export/audit.html", {
            "agents": agents,
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
        resp = self._post(request)
        if request.headers.get("X-Requested-With") == "fetch":  # live table: answer with the messages, no page reload
            from django.http import JsonResponse

            return JsonResponse({"messages": [{"level": m.level_tag, "text": str(m)} for m in messages.get_messages(request)]})
        return resp

    def _post(self, request):
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
            from ..base_config import is_backup_path

            bdir = request.POST.get("backup_dir", "").strip()[:255]
            if bdir and not is_backup_path(bdir):
                messages.error(request, t("srv.err_backup"))
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
        elif action == "keep_failed":
            st = _st()
            log = [("agent_keep_failed", str(st.agent_keep_failed), str(request.POST.get("value") == "1"))]
            st.agent_keep_failed = request.POST.get("value") == "1"
            st.save(update_fields=["agent_keep_failed"])
        elif action == "autosync":  # NetBox pushes the full CFG when a server runs another CFG: off | after X min | at HH:MM
            import re as _re

            from .agent import AUTOSYNC_MINUTES

            st = _st()
            mode = request.POST.get("mode", "off")
            mins = int(request.POST.get("minutes", "0")) if request.POST.get("minutes", "").isdigit() else st.agent_autosync_min
            at = request.POST.get("at", "").strip() or st.agent_autosync_at
            if mode not in ("off", "after", "at") or mins not in AUTOSYNC_MINUTES or not _re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", at):
                messages.error(request, t("srv.err_autosync"))
                return redirect(reverse("plugins:netbox_isc_dhcp:pluginsettings_list") + "#isc-servers")
            before = f"{st.agent_autosync} {st.agent_autosync_min} {st.agent_autosync_at}"
            st.agent_autosync, st.agent_autosync_min, st.agent_autosync_at = mode, mins, at
            st.save(update_fields=["agent_autosync", "agent_autosync_min", "agent_autosync_at"])
            log = [("agent_autosync", before, f"{mode} {mins} {at}")]
        elif action == "leases":  # periodic copy of the lease database on every server: interval + copies kept
            from .agent import LEASES_EVERY, LEASES_KEEP

            st = _st()
            ev = int(request.POST.get("every", "-1")) if request.POST.get("every", "").isdigit() else -1
            kp = int(request.POST.get("keep", "0")) if request.POST.get("keep", "").isdigit() else 0
            if ev not in LEASES_EVERY or kp not in LEASES_KEEP:
                messages.error(request, t("srv.err_leases"))
                return redirect(reverse("plugins:netbox_isc_dhcp:pluginsettings_list") + "#isc-servers")
            before = f"{st.agent_leases_every} {st.agent_leases_keep}"
            st.agent_leases_every, st.agent_leases_keep = ev, kp
            st.save(update_fields=["agent_leases_every", "agent_leases_keep"])
            log = [("agent_leases", before, f"{ev} {kp}")]
        elif action == "bundle_min":
            st = _st()
            v = int(request.POST.get("value", "0")) if request.POST.get("value", "").isdigit() else 0
            if v in (1, 5, 10, 20, 50, 100):
                log = [("agent_bundle_min", str(st.agent_bundle_min), str(v))]
                st.agent_bundle_min = v
                st.save(update_fields=["agent_bundle_min"])
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

            from .agent import first_block

            cur = first_server()
            if isc_mismatch() and cur is not None and cur.pk != srv.pk:
                messages.error(request, t("srv.err_first_isc"))
                return redirect(reverse("plugins:netbox_isc_dhcp:pluginsettings_list") + "#isc-servers")
            why = first_block(srv)
            if why:
                messages.error(request, t("srv.first_no", why=t(why)))
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
        elif action == "key_new":  # new agent API key; the old one stays valid until every server switched
            import secrets

            st = _st()
            if st.agent_key and st.agent_key_old:
                messages.error(request, t("srv.key_busy"))
                return redirect(reverse("plugins:netbox_isc_dhcp:pluginsettings_list") + "#isc-servers")
            st.agent_key_old = st.agent_key or "-"
            st.agent_key = secrets.token_hex(20)
            st.save(update_fields=["agent_key", "agent_key_old"])
            log = [("agent_key", "***" if st.agent_key_old != "-" else "", "*** (" + st.agent_key[-4:] + ")")]
        elif action == "key_finish":  # stop accepting the old key now
            st = _st()
            log = [("agent_key_old", "***", "")] if st.agent_key_old else []
            st.agent_key_old = ""
            st.save(update_fields=["agent_key_old"])
        elif action in ("start", "stop", "restart", "update") and srv:  # command for the agent, done once at its next contact
            srv.agent_cmd = f"{action}:{timezone.now().strftime('%Y%m%d%H%M%S')}"
            srv.save(update_fields=["agent_cmd"])
            log = [(f"{action} {srv.name}", "", srv.agent_cmd)]
            messages.success(request, t("srv.cmd_queued", cmd=t("srv.cmd_%s" % action), name=srv.name))
        elif action == "gh_check":  # look for a new agent on GitHub now (otherwise every 5 minutes in the background)
            from .agent import _checking, _fetch_github, agent_source

            _checking["on"] = True
            _fetch_github()
            ver, src, _, err = agent_source()
            if err:
                messages.warning(request, t("srv.agent_gh_err") + f" ({err})")
            else:
                messages.success(request, t("srv.agent_gh_done", v=ver))
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
        if not list(messages.get_messages(request)._queued_messages if hasattr(messages.get_messages(request), "_queued_messages") else []):
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
    AuditEvent.objects.create(time=timezone.now(), kind="agent", client_ip=ip, result="refused",
                              cause=t("aud.agent_refused_key", ip=ip) if getattr(request, "_isc_refused", "") == "key" else t("aud.agent_refused", ip=ip),
                              output=f"REMOTE_ADDR={request.META.get('REMOTE_ADDR', '')} X-Forwarded-For={request.META.get('HTTP_X_FORWARDED_FOR', '')}")


def _flow(output):
    """STEP lines of the agent report -> 'stiahol 1 súbor → zálohoval 1 → aplikoval 1 → test OK → reštart → dhcpd beží'."""
    parts = []
    for line in output.splitlines():
        if not line.startswith("STEP "):
            continue
        bits = line.split()
        code, n = (bits[1], bits[2] if len(bits) > 2 else "0") if len(bits) > 1 else ("", "0")
        key = f"aud.st_{code}" + ("_" + n if code == "test" else "")
        parts.append(t(key, n=n))
    return " → ".join(parts)


def _wants_text(request):
    return request.GET.get("format") == "text" or "text/plain" in request.META.get("HTTP_ACCEPT", "")


def _agent_data(request):
    """Agent request data: form fields (bash agent) or JSON body."""
    if request.method == "POST" and request.content_type == "application/json":
        body = _json_body(request)
        return body if isinstance(body, dict) else None
    return request.POST if request.method == "POST" else request.GET


@method_decorator(login_not_required, name="dispatch")  # agent / DHCP servers: no login, access = client IP
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
                "dir": managed_dirs(), "on_test_fail": "keep" if st and st.agent_keep_failed else "restore"}  # the agent sends sha256 of every file in these dirs (+ dhcpd.conf) next time
        text = _wants_text(request)

        def reply(steps, extra=None, status=200):
            d = dict(info, **(extra or {}))
            if text:
                return HttpResponse(as_text(d, steps), status=status, content_type="text/plain; charset=utf-8")
            return HttpResponse(json.dumps(dict(d, steps=steps), indent=1), status=status, content_type="application/json")

        if not ExportFile.objects.filter(area="conf").exists():  # never let a server restart without a dhcpd.conf
            return reply([], {"error": "dhcpd.conf is not generated"}, status=409)
        api = request.path_info.startswith("/api/")
        info["report"] = request.build_absolute_uri(reverse("plugins-api:netbox_isc_dhcp-api:agent_report" if api else "plugins:netbox_isc_dhcp:export_report"))
        hash_only = False
        want = dict(ExportFile.objects.values_list("path", "sha256"))
        check = build.check_hash(want)  # ONE control hash: the agent sends its file list only when its disk hash differs
        disk_hash = str((data or {}).get("disk_hash", "")).lower()
        if server is not None and _ver_ge(server.agent_version, (1, 18, 0)):  # older agents would log an unknown command
            from ..base_config import is_backup_path
            from ..models import BACKUP_DIR

            bdir = st.agent_backup_dir if st and is_backup_path(st.agent_backup_dir) else BACKUP_DIR
            every = st.agent_leases_every if st else 60
            info["leases"] = f"{every}\t{st.agent_leases_keep if st else 72}\t{bdir.rstrip('/')}/leases"
        if disk_hash:
            info["check"] = check  # only to agents that send their disk hash (1.16.0+); older ones would log it as an unknown command
        skipped = request.method == "POST" and str((data or {}).get("nofiles", "")) == "1"  # agent sent only its disk hash
        if skipped and disk_hash == check:
            have = dict(want)  # hash only and equal: the disk is exactly NetBox's CFG
        if have:  # files on the server are exactly the current set -> the agent may (re)start dhcpd itself when it is down
            if want and all(have.get(p) == h for p, h in want.items()):
                info["disk"] = "current"
        if skipped and disk_hash != check:
            hash_only = True  # hash only and different: no plan from an unknown disk, the agent asks again with its file list
        if server is not None and server.restart_req:
            info["restart_req"] = server.restart_req  # manual restart from NetBox (the agent does it once per id)
        if server is not None and server.agent_cmd:  # start | stop | restart | update, done once per id
            cmd, cid = server.agent_cmd.split(":", 1)
            info["cmd"] = f"{cmd}\t{cid}"
            if cmd == "update":
                from .agent import agent_script

                _aver, sha, _ = agent_script()  # not "ver": that one is the CFG number used below
                info["agent_url"] = request.build_absolute_uri(reverse("plugins-api:netbox_isc_dhcp-api:agent_self" if api else "plugins:netbox_isc_dhcp:export_agent_self"))
                info["agent_sha"] = sha
        _key_progress(request, server, info)
        if hash_only:
            return reply([])
        reason, names = gate(server, mh)
        if reason:
            return reply([], {"wait": reason, "wait_for": ",".join(names)})
        from .agent import autosync_due

        why = autosync_due(server, mh)
        if why:  # NetBox pushes the full CFG by itself (switch in CFG pluginu -> DHCP servery)
            AuditEvent.objects.create(time=timezone.now(), kind="agent", server=server.name, client_ip=audit.client_ip(request),
                                      manifest_hash=mh, cause=why, level="info")
        # files on the server differ from NetBox (changed / missing / extra file by hand?): by the control hash when the agent sends it
        disk_off = (disk_hash != check) if (disk_hash and have) else (bool(have) and info.get("disk") != "current")
        if mode == "export" and server is not None and server.last_result == "ok" and server.last_hash == mh and not disk_off:
            steps = []  # export = everything, but only when the set changed since this server's last OK (no restart on every poll)
        else:
            api = request.path_info.startswith("/api/")
            fname = "plugins-api:netbox_isc_dhcp-api:agent_file" if api else "plugins:netbox_isc_dhcp:export_file"
            rname = "plugins-api:netbox_isc_dhcp-api:agent_report" if api else "plugins:netbox_isc_dhcp:export_report"
            steps = make_plan(have, server, lambda p: request.build_absolute_uri(reverse(fname, kwargs={"path": quote(p.lstrip("/"))})),
                              request.build_absolute_uri(reverse(rname)), mh, mode)
            if sum(1 for x in steps if x["op"] == "download") >= (st.agent_bundle_min if st else 10):  # many files: one tar.gz
                info["bundle"] = request.build_absolute_uri(reverse("plugins-api:netbox_isc_dhcp-api:agent_bundle" if api else "plugins:netbox_isc_dhcp:export_bundle"))
        if steps and disk_off and server is not None and server.last_result == "ok" and server.last_hash == mh:
            # the server had exactly this CFG and now its files differ: changed outside NetBox -> NetBox (source of truth) puts its files back
            changed = sorted(p for p, h in want.items() if p in have and have[p] != h)
            missing = sorted(p for p in want if p not in have)
            extra = sorted(x["path"] for x in steps if x["op"] == "delete")
            AuditEvent.objects.create(time=timezone.now(), kind="agent", server=server.name, client_ip=audit.client_ip(request),
                                      result="manual", level="warn", manifest_hash=mh,
                                      cause=t("aud.cfg_manual", c=len(changed), m=len(missing), e=len(extra), cfg=ver.label if ver else ""),
                                      changes=[{"path": p, "action": "update"} for p in changed] + [{"path": p, "action": "add"} for p in missing]
                                      + [{"path": p, "action": "delete"} for p in extra])
        if steps:
            AuditEvent.objects.create(time=timezone.now(), kind="plan", server=server.name if server else "", client_ip=audit.client_ip(request),
                                      user=request.user.username if request.user.is_authenticated else "", manifest_hash=mh,
                                      cause=t("aud.plan_dl", cfg=ver.label if ver else "", n=sum(1 for x in steps if x["op"] == "download"),
                                            d=sum(1 for x in steps if x["op"] == "delete")),
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


def _ver_ge(v, want):
    """agent version string >= want tuple (unknown = False)."""
    try:
        return tuple(int(x) for x in str(v).split(".")[:3]) >= want
    except ValueError:
        return False


@method_decorator(login_not_required, name="dispatch")  # agent / DHCP servers: no login, access = client IP
@method_decorator(csrf_exempt, name="dispatch")
class ReportView(View):
    """Agent result. POST form or JSON: hash, result ok|test_failed|rolled_back|failed, output, done."""

    RESULTS = ("ok", "test_failed", "rolled_back", "failed", "start_failed")

    def post(self, request):
        from . import versions
        from .agent import server_for
        from .models import AuditEvent

        if not _client_allowed(request):
            _refused_contact(request)
            raise PermissionDenied
        body = _agent_data(request)
        if body is None or body.get("result") not in self.RESULTS:
            return HttpResponse('{"error": "result must be one of ok, test_failed, rolled_back, failed, start_failed"}', status=400, content_type="application/json")
        server = server_for(request)
        now = timezone.now()
        h = str(body.get("hash", ""))[:64]
        done = body.get("done", [])
        done = done if isinstance(done, list) else [x for x in str(done).split() if x]
        output = str(body.get("output", ""))[:20000]
        flow = _flow(output)
        AuditEvent.objects.create(time=now, kind="report", server=server.name if server else "", client_ip=audit.client_ip(request),
                                  manifest_hash=h, result=body["result"], output=output,
                                  cause=(flow + " · " if flow else "") + t("aud.result_" + body["result"]) + (f" · {versions.label(h)}" if h else ""),
                                  changes=[{"path": str(x), "action": "done"} for x in done][:2000])
        if server:
            server.last_hash, server.last_result, server.last_report = h, body["result"], now
            fields = ["last_hash", "last_result", "last_report", "disk_broken"]
            kept = str(body.get("kept", "")) in ("1", "true", "yes")
            server.disk_broken = h if body["result"] == "test_failed" and kept else ("" if body["result"] in ("ok", "start_failed") else server.disk_broken)
            run = str(body.get("running", "") or (h if body["result"] == "ok" else ""))[:64]
            if run:
                server.running_hash = run
                fields.append("running_hash")
            pid = "".join(c for c in str(body.get("pid", ""))[:10] if c.isdigit())
            if pid:
                server.dhcpd_pid = pid
                fields.append("dhcpd_pid")
            server.save(update_fields=fields)
        return HttpResponse('{"ok": true}', content_type="application/json")
