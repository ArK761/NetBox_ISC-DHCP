from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.urls import reverse
from django.shortcuts import get_object_or_404, redirect
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views import View
from netbox.object_actions import AddObject, BulkDelete, DeleteObject
from netbox.views import generic
from utilities.views import ViewTab, register_model_view

from . import forms, tables
from .i18n import t, t_lazy, tmsg
from .models import MAX_ACTIVE_DNS, PoolTemplate, SubnetConfig, BaseConfig, DHCPFile, DHCPGroup, DHCPPath, DNSServer, PluginSettings
from .services import build_base_config


def _crud(model, form_cls, table_cls, singleton=False, extra_context=None, inline_only=False):
    """Register list / detail / add / edit / delete views for a model.
    Singletons and inline_only models are edited only by clicking on their page: no Edit button, the edit URL redirects
    to the page (the generic form would bypass the checks). Singletons have no Delete either."""
    no_form = singleton or inline_only

    if singleton:
        # The list URL is the menu link. It redirects to the one object, whose URL contains the
        # menu link, so NetBox keeps the menu group expanded.
        @register_model_view(model, "list", path="", detail=False)
        class ListView(View):
            def get(self, request):
                if not request.user.has_perm(f"netbox_isc_dhcp.view_{model._meta.model_name}"):
                    raise PermissionDenied
                obj = model.objects.first() or model.objects.create()
                return redirect(obj.get_absolute_url())
    else:
        @register_model_view(model, "list", path="", detail=False)
        class ListView(generic.ObjectListView):
            queryset = model.objects.all()
            table = table_cls
            actions = (AddObject, BulkDelete)  # no import / export in this plugin

        @register_model_view(model, "bulk_delete", path="delete", detail=False)
        class BulkDeleteView(generic.BulkDeleteView):
            queryset = model.objects.all()
            table = table_cls
            template_name = "netbox_isc_dhcp/bulk_delete.html"  # no changelog message / background job

    @register_model_view(model)
    class DetailView(generic.ObjectView):
        queryset = model.objects.all()
        template_name = f"netbox_isc_dhcp/{model._meta.model_name}.html"
        if no_form:
            actions = () if singleton else (DeleteObject,)

        def get_extra_context(self, request, instance):
            return extra_context(request, instance) if extra_context else {}

    if no_form:
        @register_model_view(model, "edit")
        class InlineOnlyView(View):
            def get(self, request, pk):
                return redirect(get_object_or_404(model, pk=pk).get_absolute_url())

            post = get

        if not singleton:
            @register_model_view(model, "add", detail=False)
            class AddView(generic.ObjectEditView):
                queryset = model.objects.all()
                form = form_cls
    else:
        @register_model_view(model, "add", detail=False)
        @register_model_view(model, "edit")
        class EditView(generic.ObjectEditView):
            queryset = model.objects.all()
            form = form_cls

    @register_model_view(model, "delete")
    class DeleteView(generic.ObjectDeleteView):
        """Delete confirmation without changelog message."""

        queryset = model.objects.all()
        template_name = "netbox_isc_dhcp/object_delete.html"

        def get(self, request, *args, **kwargs):
            from utilities.htmx import htmx_partial

            if not htmx_partial(request):
                return super().get(request, *args, **kwargs)
            from django.shortcuts import render
            from utilities.forms import DeleteForm
            from utilities.views import get_action_url

            obj = self.get_object(**kwargs)
            try:
                dependent_objects = self._get_dependent_objects(obj)
            except Exception:
                return super().get(request, *args, **kwargs)
            return render(request, "netbox_isc_dhcp/delete_form.html", {
                "object": obj,
                "object_type": self.queryset.model._meta.verbose_name,
                "form": DeleteForm(instance=obj, initial=request.GET),
                "form_url": get_action_url(self.queryset.model, action="delete", kwargs={"pk": obj.pk}),
                "dependent_objects": dependent_objects,
                **self.get_extra_context(request, obj),
            })

    return ListView, DetailView, (AddView if not singleton else None) if no_form else EditView, DeleteView


# --- Base config -----------------------------------------------------------------
_crud(BaseConfig, forms.BaseConfigForm, tables.BaseConfigTable, singleton=True,
      extra_context=lambda request, instance: _baseconfig_context(request, instance))


@register_model_view(BaseConfig, name="preview", path="preview")
class BaseConfigPreviewView(generic.ObjectView):
    queryset = BaseConfig.objects.all()
    template_name = "netbox_isc_dhcp/baseconfig_preview.html"
    tab = ViewTab(label=t_lazy("tab.preview"))

    def get_extra_context(self, request, instance):
        text, warnings = build_base_config(instance)
        return {"generated": text, "warnings": warnings}


# --- DHCP groups -----------------------------------------------------------------
_crud(DHCPGroup, forms.DHCPGroupForm, tables.DHCPGroupTable)

# --- DNS -------------------------------------------------------------------------
_crud(DNSServer, forms.DNSServerForm, tables.DNSServerTable)


def _ago(when):
    from django.utils import timezone

    n = max(0, int((timezone.now() - when).total_seconds()))
    if n < 60:
        return t("ago.s", n=n)
    if n < 3600:
        return t("ago.m", n=n // 60)
    if n < 86400:
        return t("ago.h", n=n // 3600)
    return t("ago.d", n=n // 86400)


def _sync_hint(srv, st, mh):
    """Text under an older CFG: when NetBox pushes the full CFG by itself (auto CFG sync), or ""."""
    from django.utils import timezone

    from .export.agent import FAILED

    if not st or st.agent_autosync not in ("after", "at") or not srv.running_hash or srv.running_hash == mh:
        return ""
    if srv.last_result in FAILED and srv.last_hash == mh:
        return t("srv.autosync_failed")
    if st.agent_autosync == "after":
        since = srv.mismatch_since or timezone.now()
        eta = timezone.localtime(since + __import__("datetime").timedelta(minutes=st.agent_autosync_min or 15))
        return t("srv.autosync_eta", at=eta.strftime("%H:%M"))
    return t("srv.autosync_eta", at=st.agent_autosync_at)


def _first_leases(srv):
    """First run of the agent: when / how many IPs / sha / where the original leases were copied."""
    from .export.agent import fmt_time

    p = (srv.first_leases or "").split("|")
    if len(p) != 4 or not p[0].isdigit():
        return None
    return {"when": fmt_time(p[0]), "n": p[1], "sha": p[2][:12], "path": p[3]}


def _server_rows():
    from django.utils import timezone
    from .export.models import DHCPServer
    from .export.servers import resolve

    from .export import build, versions
    from .export.agent import disk_rows, first_block, fmt_time, gate, stale
    from .export.views import key_hash
    from .models import settings_obj

    st = settings_obj()
    interval = st.agent_interval if st else 60
    mh = build.manifest_hash()
    ck = build.check_hash()  # ONE control hash of the whole CFG (compared with the agent's disk hash)
    versions.ensure(mh)  # the current set always has a number (also right after a plugin update)
    lab = versions.labels()
    out = []
    for srv in DHCPServer.objects.order_by("pk"):
        ips, err = resolve(srv.address)
        reason, names = gate(srv, mh) if srv.enabled and srv.last_seen else ("", [])  # no agent yet: nothing to wait for
        wait = t(f"srv.wait_{reason}", names=", ".join(names)) if reason else ""
        fb = first_block(srv)
        from .export.agent import agent_outdated

        cmd = srv.agent_cmd.split(":", 1)[0] if srv.agent_cmd else ""
        out.append({"s": srv, "ips": ips, "err": err, "wait": wait, "reason": reason, "names": names, "first_why": t(fb) if fb else "", "outdated": agent_outdated(srv),
                    "cmd_pending": t("srv.cmd_%s" % cmd) if cmd else "",
                    "dhcpd_since": timezone.localtime(srv.dhcpd_since).strftime("%d.%m. %H:%M") if srv.dhcpd_since else "",
                    "dhcpd_by": t("srv.by_%s" % srv.dhcpd_by) if srv.dhcpd_by else "",
                    "key_pending": bool(st and st.agent_key and st.agent_key_old and srv.enabled and srv.last_seen and srv.key_hash != key_hash(st.agent_key)),
                    "stale": srv.enabled and srv.last_seen is not None and stale(srv, interval),
                    "ago": _ago(srv.last_seen) if srv.last_seen else "",
                    "run_label": lab.get(srv.running_hash, srv.running_hash[:12]) if srv.running_hash else "",
                    "run_ok": srv.running_hash == mh, "cur_label": lab.get(mh, mh[:12]), "svc_why": __import__("netbox_isc_dhcp.export.agent", fromlist=["x"]).svc_text(srv.svc_why) if srv.svc_why else "", "why": __import__("netbox_isc_dhcp.export.agent", fromlist=["x"]).why_text(srv.dhcpd_why) if srv.dhcpd_why else "", "last_label": lab.get(srv.last_hash, srv.last_hash[:12]) if srv.last_hash else "",
                    "sync_hint": _sync_hint(srv, st, mh),
                    "disk": ("ok" if srv.disk_hash == ck else "bad") if srv.disk_hash and srv.enabled else "",
                    "first_leases": _first_leases(srv),
                    "rl_block": __import__("netbox_isc_dhcp.export.agent", fromlist=["x"]).restore_block(srv, mh),
                    "rl_done": (lambda p: {"when": fmt_time(p[0]), "txt": p[1] if len(p) > 1 else ""} if p and p[0].isdigit() else None)(srv.leases_restored.split("|", 1)),
                    "leases_kept": (lambda k: {"b": k[0], "a": k[1], "path": k[2], "ok": int(k[1]) >= int(k[0])} if len(k) == 3 and k[0].isdigit() and k[1].isdigit() else None)(srv.leases_kept.split("|")),
                    "leases_last": fmt_time(srv.leases_last),
                    "disk_rows": disk_rows(srv.disk_usage) if srv.enabled else [],
                    "test_until": timezone.localtime(srv.test_until) if srv.is_test and srv.test_until and srv.test_until > timezone.now() and srv.dhcpd_running is not False else None,
                    "admin_off": srv.dhcpd_by == "admin" and srv.dhcpd_running is False,
                    "run_min": __import__("netbox_isc_dhcp.export.agent", fromlist=["x"]).TEST_RUN_MIN if srv.is_test else (),
                    "test_state": ("ok" if srv.test_ok_hash == mh else ("failed" if srv.last_hash == mh and srv.last_result and srv.last_result != "ok"
                                   else ("running" if srv.last_hash == mh and srv.last_result == "ok" else "pending"))) if srv.is_test and srv.enabled else "",
                    "leases_old": bool(srv.leases_last and st and st.agent_leases_every and (timezone.now() - srv.leases_last).total_seconds() > st.agent_leases_every * 60 * 2 + 600)})
    waited = {n for r in out if r["reason"] == "staged" for n in r["names"]}
    for r in out:
        r["blocks"] = r["s"].name in waited  # others wait for this server: admin may let them go on
    return out


class AgentPageView(LoginRequiredMixin, View):
    """Agent (menu): read-only list of the commands the agent knows (nothing can be changed here)."""

    def get(self, request):
        from django.shortcuts import render

        from .export import agent as ag

        if not request.user.has_perm("netbox_isc_dhcp.view_pluginsettings"):
            raise PermissionDenied
        loc = ag._local_agent().decode("utf-8", "replace")
        import re

        m = re.search(r'^DHCP_SERVICE="([^"]*)"', loc, re.M)
        return render(request, "netbox_isc_dhcp/agent.html", {
            "agent_commands": ag.command_rows(), "agent_self": ag.self_rows(), "agent_version": ag._ver(ag._local_agent()),
            "test_cmd": ag.TEST_CMD.replace("{conf}", "/etc/dhcp/dhcpd.conf"), "restart_cmd": ag.RESTART_CMD,
            "service": m.group(1) if m else "isc-dhcp-server"})


class NoticesView(LoginRequiredMixin, View):
    """Warning bars at the top of plugin pages, refreshed live (no page reload needed)."""

    def get(self, request):
        from django.http import HttpResponse

        from .middleware import DNSWarningMiddleware, notices_html

        try:
            html = notices_html(DNSWarningMiddleware(None)._notices(request), (t("lbl.tree_show"), t("lbl.tree_hide")), request)
        except Exception:
            return HttpResponse(status=204)
        r = HttpResponse(html, content_type="text/html; charset=utf-8")
        r["Cache-Control"] = "no-store"
        return r


class ServersTableView(LoginRequiredMixin, View):
    """Live part of CFG pluginu -> DHCP servery (refreshed every 5 s on the page)."""

    def get(self, request):
        from django.shortcuts import render

        from .export import build
        from .export.agent import isc_mismatch

        if not request.user.has_perm("netbox_isc_dhcp.view_pluginsettings"):
            raise PermissionDenied
        return render(request, "netbox_isc_dhcp/_servers_table.html", {
            "servers": _server_rows(), "first_pk": _first_pk(), "isc_lock": isc_mismatch(), "current_hash": build.manifest_hash(), "check_hash": build.check_hash(), "leases_on": bool(getattr(__import__("netbox_isc_dhcp.models", fromlist=["x"]).settings_obj(), "agent_leases_every", 0)), "current_label": __import__("netbox_isc_dhcp.export.versions", fromlist=["x"]).label(build.manifest_hash(), create=True),
            "agent_latest": __import__("netbox_isc_dhcp.export.agent", fromlist=["x"]).agent_script()[0], "agent_src": _agent_src()})


def _agent_src():
    import datetime


    from .export.agent import GITHUB_AGENT, agent_source

    ver, src, checked, err = agent_source()
    when = _ago(datetime.datetime.fromtimestamp(checked, tz=datetime.timezone.utc)) if checked else ""
    return {"ver": ver, "src": src, "when": when, "err": err, "url": GITHUB_AGENT}


def _first_pk():
    from .export.models import DHCPServer

    f = DHCPServer.objects.order_by("order", "pk").first()
    return f.pk if f else None


# --- Plugin settings: language, dhcpd.conf path, base path and subdirectories ---
_crud(PluginSettings, forms.PluginSettingsForm, tables.PluginSettingsTable, singleton=True,
      extra_context=lambda request, instance: {
          "servers": _server_rows(), "first_pk": _first_pk(),
          "current_hash": __import__("netbox_isc_dhcp.export.build", fromlist=["manifest_hash"]).manifest_hash(),
          "check_hash": __import__("netbox_isc_dhcp.export.build", fromlist=["x"]).check_hash(),
          "current_label": __import__("netbox_isc_dhcp.export.versions", fromlist=["x"]).label(__import__("netbox_isc_dhcp.export.build", fromlist=["manifest_hash"]).manifest_hash(), create=True),
          "intervals": [(v, f"{v} s" if v < 60 else f"{v // 60} min") for v in __import__("netbox_isc_dhcp.export.agent", fromlist=["x"]).INTERVALS],
          "isc_lock": __import__("netbox_isc_dhcp.export.agent", fromlist=["x"]).isc_mismatch(),
          "agent_latest": __import__("netbox_isc_dhcp.export.agent", fromlist=["x"]).agent_script()[0],
          "agent_src": _agent_src(),
          "autosync_minutes": __import__("netbox_isc_dhcp.export.agent", fromlist=["x"]).AUTOSYNC_MINUTES,
          "leases_every": [(v, t("srv.leases_off") if v == 0 else (f"{v} min" if v < 60 else f"{v // 60} h")) for v in __import__("netbox_isc_dhcp.export.agent", fromlist=["x"]).LEASES_EVERY],
          "leases_keep": __import__("netbox_isc_dhcp.export.agent", fromlist=["x"]).LEASES_KEEP,
          "time_formats": [(k, t("tf." + k), __import__("django.utils.timezone", fromlist=["x"]).localtime().strftime(f)) for k, (lbl, f) in __import__("netbox_isc_dhcp.export.agent", fromlist=["x"]).TIME_FORMATS.items()],
          "leases_on": bool(instance.agent_leases_every) if instance else False,
          "bundle_choices": (1, 5, 10, 20, 50, 100),
          "agent_api_url": request.build_absolute_uri(reverse("plugins-api:netbox_isc_dhcp-api:agent_plan")),
          "agent_hint": t("srv.agent", plan=request.build_absolute_uri(reverse("plugins:netbox_isc_dhcp:export_plan")),
                          report=request.build_absolute_uri(reverse("plugins:netbox_isc_dhcp:export_report"))),
          "subdirs": DHCPPath.objects.all(),
          "dir_rows": [("table_dir", "lbl.table_dir", instance.table_dir), ("subnet_dir", "lbl.subnet_dir2", instance.subnet_dir)],
          "path_rows": [
              ("base_path", "lbl.base_path", instance.base_path, "/opt/dhcp"),
          ],
      })


# --- DNS checkbox ----------------------------------------------------------------
class DNSServerToggleView(View):
    def post(self, request, pk):
        if not request.user.has_perm("netbox_isc_dhcp.change_dnsserver"):
            messages.error(request, "Permission denied.")
            return redirect("plugins:netbox_isc_dhcp:dnsserver_list")
        obj = get_object_or_404(DNSServer, pk=pk)
        if not obj.active and DNSServer.objects.filter(active=True).count() >= MAX_ACTIVE_DNS:
            messages.error(request, t("err.max_dns", n=MAX_ACTIVE_DNS))
        else:
            obj.active = not obj.active
            obj.save()
        return redirect("plugins:netbox_isc_dhcp:dnsserver_list")


register_model_view(DNSServer, "toggle", path="toggle")(DNSServerToggleView)


# --- Directories and files ---------------------------------------------------------
_crud(DHCPPath, forms.DHCPPathForm, tables.DHCPPathTable)
_crud(DHCPFile, forms.DHCPFileForm, tables.DHCPFileTable)


@register_model_view(DHCPFile, name="preview", path="preview")
class DHCPFilePreviewView(generic.ObjectView):
    """Shows the STORED file. Nothing is generated here (except once for a file that never was)."""

    queryset = DHCPFile.objects.all()
    template_name = "netbox_isc_dhcp/dhcpfile_preview.html"
    tab = ViewTab(label=t_lazy("tab.preview"))

    def get_extra_context(self, request, instance):
        if instance.generated is None:
            from .services import regenerate_file

            regenerate_file(instance)
        return {"line_count": instance.content.count("\n")}


class DHCPFileRegenerateView(View):
    def post(self, request, pk):
        from .services import regenerate_file

        obj = get_object_or_404(DHCPFile.objects.select_related("group__group", "directory"), pk=pk)
        if not request.user.has_perm("netbox_isc_dhcp.change_dhcpfile"):
            raise PermissionDenied
        changed = regenerate_file(obj)
        messages.success(request, t("msg.regen_changed" if changed else "msg.regen_same"))
        return redirect("plugins:netbox_isc_dhcp:dhcpfile_preview", pk=obj.pk)


register_model_view(DHCPFile, "regenerate", path="regenerate")(DHCPFileRegenerateView)


# --- Inline editing on the settings page (click a value, type, save) -------------
class PluginSettingsInlineView(View):
    FIELDS = ("language", "base_path", "table_dir", "subnet_dir")  # dhcpd.conf directory is fixed: /etc/dhcp

    def post(self, request, pk):
        if not request.user.has_perm("netbox_isc_dhcp.change_pluginsettings"):
            raise PermissionDenied
        obj = get_object_or_404(PluginSettings, pk=pk)
        field = request.POST.get("field")
        if field == "notices_open":  # display only: never regenerates the CFG
            obj.notices_open = request.POST.get("value") == "1"
            obj.save(update_fields=["notices_open"])
            messages.success(request, t("msg.saved"))
        elif field in self.FIELDS:
            value = request.POST.get("value", "").strip()
            if field in ("table_dir", "subnet_dir"):
                field, value = f"{field}_id", (int(value) if value.isdigit() else None)
            setattr(obj, field, value)
            try:
                obj.full_clean()
                obj.save()
                messages.success(request, t("msg.saved"))
            except ValidationError as exc:
                messages.error(request, "; ".join(m for ms in exc.message_dict.values() for m in ms))
        return redirect(obj.get_absolute_url())


class DHCPPathInlineView(View):
    """Add a subdirectory (no pk) or rename one (pk) right on the settings page."""

    def post(self, request, pk=None):
        perm = "change_dhcppath" if pk else "add_dhcppath"
        if not request.user.has_perm(f"netbox_isc_dhcp.{perm}"):
            raise PermissionDenied
        obj = get_object_or_404(DHCPPath, pk=pk) if pk else DHCPPath(order=(DHCPPath.objects.count() + 1) * 10)
        obj.name = request.POST.get("value", "").strip()
        try:
            obj.full_clean()
            obj.save()
            messages.success(request, t("msg.saved"))
        except ValidationError as exc:
            messages.error(request, "; ".join(m for ms in exc.message_dict.values() for m in ms))
        st = PluginSettings.objects.first()
        return redirect(st.get_absolute_url() if st else "plugins:netbox_isc_dhcp:pluginsettings_list")


class BaseConfigInlineView(View):
    """Click-to-edit of the static part of dhcpd.conf."""

    def post(self, request, pk):
        if not request.user.has_perm("netbox_isc_dhcp.change_baseconfig"):
            raise PermissionDenied
        obj = get_object_or_404(BaseConfig, pk=pk)
        if request.POST.get("field") == "static_text":
            obj.static_text = request.POST.get("value", "")
            obj.save()
            messages.success(request, t("msg.saved"))
        return redirect(obj.get_absolute_url())


class SubnetConfigInlineView(View):
    """Click-to-edit on the subnets page: object, conditions (ticked values, include/exclude), pool type field."""

    def post(self, request, pk):
        from .source_fields import distinct_values, field_options, get_model

        if not request.user.has_perm("netbox_isc_dhcp.change_subnetconfig"):
            raise PermissionDenied
        obj = get_object_or_404(SubnetConfig, pk=pk)
        model = get_model(obj.source_model)
        action, value = request.POST.get("field"), request.POST.get("value", "").strip()
        idx = request.POST.get("index", "")
        idx = int(idx) if idx.isdigit() else None
        conds = [dict(c) for c in obj.conditions or []]
        row = conds[idx] if idx is not None and idx < len(conds) else None
        if action == "source_model":
            if value and get_model(value) is None:
                messages.error(request, "Unknown object type.")
                return redirect(obj.get_absolute_url())
            if value != obj.source_model:
                conds = []
            obj.source_model = value
        elif action == "cond_add" and value in {o["key"] for o in field_options(model)}:
            conds.append({"field": value, "values": [], "mode": "include"})
        elif row is not None and action == "cond_set":
            ticked = request.POST.getlist("values")
            total = len(distinct_values(model, row["field"]))
            row["mode"] = "exclude" if request.POST.get("mode") == "exclude" else "include"
            row["all"] = bool(total) and len(set(ticked)) >= total  # all ticked -> flag only, no long list
            row["values"] = [] if row["all"] else ticked
            row.pop("value", None)
        elif row is not None and action == "cond_all":
            row["all"], row["values"] = True, []
            row.pop("value", None)
        elif row is not None and action == "cond_none":
            row["all"], row["values"] = False, []
            row.pop("value", None)
        elif action == "gateway_mode" and value in ("first", "last"):
            obj.gateway_mode = value
        elif action in ("include_subnets", "include_each"):
            setattr(obj, action, value == "1")
        elif action == "subnet_dir":
            from .models import settings_obj

            st = settings_obj() or PluginSettings.objects.create()
            st.subnet_dir_id = int(value) if value.isdigit() and DHCPPath.objects.filter(pk=int(value)).exists() else None
            st.save()
        elif row is not None and action in ("cond_poolkey", "cond_poolkey_off", "cond_del") and (action != "cond_del" or row.get("pool_key")) \
                and (locked := _pool_key_locked(conds, row, action)):
            messages.error(request, locked)  # pools in the CFG for the DHCP servers: never changed just like that
            return redirect(obj.get_absolute_url())
        elif row is not None and action == "cond_poolkey_off":
            row["pool_key"] = False  # no pool type = no pools
        elif row is not None and action == "cond_poolkey" and len(distinct_values(model, row["field"])) > MAX_POOLS:
            messages.error(request, t("err.pool_key_many", n=len(distinct_values(model, row["field"])), max=MAX_POOLS))
            return redirect(obj.get_absolute_url())
        elif row is not None and action == "cond_poolkey":
            for c in conds:
                c["pool_key"] = False
            row["pool_key"] = True
        elif row is not None and action == "cond_del":
            conds.pop(idx)
        elif action == "pool_prepare" and value:  # a pool for one value of the pool type field (object id), code written in advance
            from .newvalues import _candidates

            key = next((c for c in conds if c.get("pool_key") and c.get("field")), None)
            name = dict((str(v), str(n)) for v, n in _candidates(model, key["field"])).get(value) if key else None
            if name:
                pt = PoolTemplate.objects.filter(ref=value).first() or PoolTemplate.objects.filter(name=name[:100]).first()
                if pt is None:
                    pt = PoolTemplate.objects.create(name=name[:100], ref=value, enabled=False)
                return redirect(pt.get_absolute_url())
            return redirect(obj.get_absolute_url())
        elif row is not None and action == "cond_ignore" and value:  # warnings bar: 'Nepoužívať' = never report this value
            ign = [str(v) for v in row.get("ignored") or []]
            if value not in ign:
                row["ignored"] = ign + [value]
        elif row is not None and action == "cond_unignore":  # report it again
            row["ignored"] = [str(v) for v in row.get("ignored") or [] if str(v) != value]
        obj.conditions = conds
        obj.save()
        messages.success(request, t("msg.saved"))
        nxt = request.POST.get("next", "")
        from django.utils.http import url_has_allowed_host_and_scheme

        if action in ("cond_ignore", "cond_unignore") and nxt and url_has_allowed_host_and_scheme(nxt, {request.get_host()}):
            return redirect(nxt)  # back to the page where 'Nepoužívať' was clicked
        return redirect(obj.get_absolute_url())


def _baseconfig_context(request, instance):
    from .models import settings_obj
    from .services import subnet_includes_paths, table_includes

    st = settings_obj()
    includes, warnings = table_includes()
    subs, w2 = subnet_includes_paths()
    warnings = warnings + w2
    from .models import CONF_DIR

    path = f"{CONF_DIR}/{instance.name}"
    return {"file_path": path, "includes": includes, "subnet_includes": subs, "include_warnings": warnings}


# --- DHCP-CFG hub: the menu item that leads to all DHCP configuration parts ------
class DHCPHubView(LoginRequiredMixin, View):
    def get(self, request):
        from django.shortcuts import render

        items = [
            ("plugins:netbox_isc_dhcp:baseconfig_list", "mdi-file-cog-outline", "menu.base", "hub.base"),
            ("plugins:netbox_isc_dhcp:dnsserver_list", "mdi-dns-outline", "menu.dns", "hub.dns"),
            ("plugins:netbox_isc_dhcp:subnetconfig_list", "mdi-ip-network-outline", "menu.subnets", "hub.subnets"),
            ("plugins:netbox_isc_dhcp:hosts", "mdi-lan-connect", "menu.hosts", "hub.hosts"),
            ("plugins:netbox_isc_dhcp:variables", "mdi-variable", "menu.vars", "hub.vars"),
            ("plugins:netbox_isc_dhcp:export", "mdi-file-tree-outline", "menu.export", "hub.export"),
        ]
        return render(request, "netbox_isc_dhcp/dhcp_hub.html", {"items": items})


def _pool_key_locked(conds, row, action) -> str:
    """'' or why the pool type may not change now: subnets of the current pools are in the CFG for the DHCP servers."""
    current = next((c for c in conds if c.get("pool_key")), None)
    if current is None or (action == "cond_poolkey" and current is row):
        return ""  # setting the first pool type (or the same row) never breaks a running CFG
    from collections import Counter

    from .export import build
    from .export.models import DHCPServer, ExportFile

    # owner: only while a DHCP server actually runs dhcpd; without active servers the pool type is free
    active = list(DHCPServer.objects.filter(enabled=True, dhcpd_running=True).values_list("name", flat=True))
    if not active:
        return ""
    live = set(ExportFile.objects.filter(area="subnet").values_list("key", flat=True))
    if not live:
        return ""
    per_pool = Counter(v[1].name for pk, v in build._subnet_plan().items() if f"subnet:{pk}" in live)
    n = sum(per_pool.values()) or len(live)
    names = ", ".join(sorted(per_pool)[:6]) + (" …" if len(per_pool) > 6 else "")
    return t("err.pool_key_live", n=n, names=names or "—", servers=", ".join(sorted(active)))


def _pool_info(instance):
    """(model, matched queryset, pool key condition) of the subnet config."""
    from .source_fields import build_q, get_model

    model = get_model(instance.source_model)
    if model is None:
        return None, None, None
    active = [c for c in instance.conditions or [] if c.get("field")]
    qs = model.objects.filter(build_q(model, active))
    key = next((c for c in active if c.get("pool_key")), None)
    return model, qs, key


MAX_POOLS = 100


def _pool_names_raw(model, qs, key) -> list[tuple[str, str]]:
    """Pools = (value, name) of the pool type field. Names (e.g. WorkStation) are shown, values are used to filter."""
    from .source_fields import cond_values, distinct_values

    options = distinct_values(model, key["field"])
    label = dict(options)
    if key.get("mode", "include") == "include" and cond_values(key) and not key.get("all"):
        chosen = set(cond_values(key))
        return [(v, l) for v, l in options if v in chosen]
    f = key["field"]
    lookup = f"custom_field_data__{f[3:]}" if f.startswith("cf_") else f
    used = set()
    for v in qs.values_list(lookup, flat=True).distinct()[: MAX_POOLS * 20]:
        for i in (v if isinstance(v, list) else [v]):
            if i not in (None, ""):
                used.add(str(i))
    return [(v, l) for v, l in options if v in used] or [(v, label.get(v, v)) for v in sorted(used)]


def _pool_names(model, qs, key) -> list[tuple[str, str]]:
    pairs = _pool_names_raw(model, qs, key)
    _sync_pools(pairs)
    return pairs


def _sync_pools(pairs):
    """A pool belongs to the VALUE of the pool type field (object id), not to its name: a renamed object (tenant group
    XXX -> ZZZ) renames its pool and keeps the code. Pools from before (no value stored) are paired by name once."""
    if not pairs:
        return
    by_ref = {p.ref: p for p in PoolTemplate.objects.exclude(ref="")}
    names = set(PoolTemplate.objects.values_list("name", flat=True))
    renamed = False
    for value, name in pairs:
        name = str(name)[:100]
        pt = by_ref.get(str(value))
        if pt is not None:
            if pt.name != name and name not in names:  # never over another pool of that name (it would be ambiguous)
                PoolTemplate.objects.filter(pk=pt.pk).update(name=name)
                names.discard(pt.name)
                names.add(name)
                renamed = True
        elif name in names:
            PoolTemplate.objects.filter(name=name, ref="").update(ref=str(value))
    if renamed:
        from . import compat

        compat.invalidate()


def _class_context():
    """Subnety card: dynamic classes (from the stored group files) with their use, and classes used but not existing."""
    from .hosts.usage import references, usage_of
    from .hosts.views import _usage_rows
    from .services import check_context, dynamic_classes

    refs, dyn = references(), dynamic_classes()
    known = dyn | set(check_context()["site"].get("classes", ()))
    unknown = [{"name": n, "uses": [u for u in us if u["where"] != "static"]} for n, us in sorted(refs.items()) if n not in known]
    return {"classes": _usage_rows(usage_of(sorted(dyn, key=str.lower), refs)), "unknown_classes": [u for u in unknown if u["uses"]]}


def _pool_source_obj(model, key):
    """What the values of the pool type field are: the object type of an object custom field (e.g. 'Tenant group')."""
    from .source_fields import _custom_field

    cf = _custom_field(model, key["field"]) if key["field"].startswith("cf_") else None
    if cf is not None and cf.type in ("object", "multiobject") and cf.related_object_type is not None:
        m = cf.related_object_type.model_class()
        if m is not None:
            from django.utils import translation

            with translation.override("en"):
                return f"{m._meta.app_config.verbose_name} › {str(m._meta.verbose_name).capitalize()}"
    return ""


def _prepared_pools(model, key, active):
    """Owner: exactly the values of the pool type field (e.g. tenant groups) WITHOUT an active pool, one row each:
    a pool already prepared (code, Generate, delete) or the button 'Pripraviť'. Pools whose object no longer exists
    (or old pools of another field, e.g. YES/True) are listed apart. Never in the CFG."""
    from .newvalues import _candidates

    cand = [(str(v), str(n)) for v, n in _candidates(model, key["field"])]
    act = {p["obj"].pk for p in active}
    by_ref = {p.ref: p for p in PoolTemplate.objects.exclude(ref="")}
    by_name = {p.name: p for p in PoolTemplate.objects.all()}
    rows, used = [], set(act)
    for v, n in cand:
        pt = by_ref.get(v) or (by_name.get(n[:100]) if by_name.get(n[:100]) and not by_name[n[:100]].ref else None)
        if pt is not None and pt.pk in act:
            continue  # active pool: shown in the pools table above
        if pt is not None and not pt.ref:
            PoolTemplate.objects.filter(pk=pt.pk).update(ref=v)  # pair the old pool with its object now
            pt.ref = v
        rows.append({"value": v, "name": n, "obj": pt})
        if pt is not None:
            used.add(pt.pk)
    orphans = list(PoolTemplate.objects.exclude(pk__in=used).order_by("name"))
    return rows, orphans


def _ignored_rows(model, c):
    """Values marked 'Nepoužívať' in the warnings bar (not reported as new): [(value, name)]."""
    ign = [str(v) for v in c.get("ignored") or []]
    if not ign:
        return []
    from .newvalues import _candidates

    names = dict(_candidates(model, c.get("field")))
    return [(v, names.get(v, v)) for v in ign]


def _subnetconfig_context(request, instance):
    from .source_fields import (_field_q, cond_values, distinct_values, field_options, is_active, label_for,
                                source_label, source_models)

    model, qs, key = _pool_info(instance)
    editing = request.GET.get("edit", "")
    rows = []
    for i, c in enumerate(instance.conditions or []):
        vals = cond_values(c)
        mode = c.get("mode", "include")
        is_open = editing == str(i)
        # the (possibly long) list of values is rendered only for the row that is being edited
        options = distinct_values(model, c.get("field")) if (is_open or c.get("all")) else []
        if c.get("all"):
            vals = [v for v, _ in options]
            summary = t("lbl.none_selected") if mode == "exclude" else t("lbl.all_values", n=len(options))
        else:
            summary = (t("lbl.all_except", n=len(vals)) if mode == "exclude" else t("lbl.n_selected", n=len(vals))) if vals else ""
        can_key = bool(c.get("pool_key")) or len(options or distinct_values(model, c.get("field"))) <= MAX_POOLS  # switch usable
        rows.append({"index": i, "key": c.get("field"), "label": label_for(model, c.get("field")), "values": set(vals), "mode": mode,
                     "pool_key": bool(c.get("pool_key")), "summary": summary, "options": options if is_open else [], "open": is_open,
                     "can_key": can_key, "ignored": _ignored_rows(model, c) if is_open else []})
    groups = {}
    for value, app, label in source_models():
        groups.setdefault(app, []).append((value, label))
    any_active = any(is_active(c) for c in instance.conditions or [])
    count = qs.count() if qs is not None and any_active else 0
    pools, pools_error = [], ""
    if key is not None and any_active:
        names = _pool_names(model, qs, key)
        if len(names) > MAX_POOLS:
            pools_error = t("err.pool_key_many", n=len(names), max=MAX_POOLS)
        else:
            from .compat import incompatible

            bad = incompatible()
            from django.db.models import Count

            from .models import SubnetOverride

            ovr = dict(SubnetOverride.objects.values_list("pool_id").annotate(n=Count("id")))
            from .hosts.classes import class_files

            _cfiles = class_files()
            for value, name in names:
                pt, _ = PoolTemplate.objects.get_or_create(name=name[:100], defaults={"enabled": False, "ref": str(value)})  # owner: a new pool never goes to the CFG by itself
                lo, hi = pt.allowed_range()
                pools.append({"obj": pt, "count": qs.filter(_field_q(model, key["field"], [value])).count(),
                              "range": f"/{lo} – /{hi}" if lo else "—", "bad": sum(1 for x in bad if x["pool_pk"] == pt.pk),
                              "ovr": ovr.get(pt.pk, 0), "lit": len(__import__("netbox_isc_dhcp.hosts.classes", fromlist=["x"]).literal_lines(pt.template)),
                              "uses": __import__("netbox_isc_dhcp.hosts.classes", fromlist=["x"]).code_uses(pt.template, _cfiles)})
    prepared, orphans = _prepared_pools(model, key, pools) if key is not None and not pools_error else ([], [])
    return {"source_groups": groups, "source_label": source_label(instance.source_model), "field_options": field_options(model),
            "cond_rows": rows, "matched_count": count, "has_pool_key": key is not None, "pools": pools, "pools_error": pools_error,
            "prepared": prepared, "orphans": orphans, "pool_source_obj": _pool_source_obj(model, key) if key is not None else "", "pool_field_label": label_for(model, key["field"]) if key is not None else "",
            "incompatible": [dict(x, reason=tmsg(x["reason"])) for x in __import__("netbox_isc_dhcp.compat", fromlist=["x"]).incompatible()] if key is not None and any_active else [],
            "overrides": __import__("netbox_isc_dhcp.compat", fromlist=["x"]).overrides(),
            **_class_context(),
            "gateway_label": t("lbl.gw_first") if instance.gateway_mode == "first" else t("lbl.gw_last"),
            "subdirs": DHCPPath.objects.all(), "subnet_dir": getattr(__import__("netbox_isc_dhcp.models", fromlist=["x"]).settings_obj(), "subnet_dir", None),
            "matched_text": t("lbl.matched", n=count) if any_active else t("lbl.matched_none")}


_crud(SubnetConfig, forms.SubnetConfigForm, tables.SubnetConfigTable, singleton=True,
      extra_context=lambda request, instance: _subnetconfig_context(request, instance))



# --- Pools: template (code) per pool type, preview on a real prefix ---------------
def _pooltemplate_context(request, instance):
    from .models import DNSServer
    from .source_fields import _field_q
    from .services import variable_snippets
    from .subnet_render import render_subnet

    cfg = SubnetConfig.objects.first()
    model, qs, key = _pool_info(cfg) if cfg else (None, None, None)
    value = None
    if key is not None:
        value = next((v for v, l in _pool_names(model, qs, key) if l == instance.name), None)
    prefixes = list(qs.filter(_field_q(model, key["field"], [value]))[:2000]) if value is not None else []
    chosen = next((p for p in prefixes if str(p.pk) == request.GET.get("p")), prefixes[0] if prefixes else None)
    text, errors = "", []
    if chosen is not None:
        dns = list(DNSServer.objects.filter(active=True).values_list("ip", flat=True))
        text, errors = render_subnet(instance.template, str(getattr(chosen, "prefix", "")), dns,
                                     {"obj": chosen, "cf": getattr(chosen, "custom_field_data", {}) or {}},
                                     gateway_mode=cfg.gateway_mode if cfg else "first", snippets=variable_snippets(),
                                     **__import__("netbox_isc_dhcp.services", fromlist=["x"]).check_context())
    from .compat import incompatible, ranges_text, suitable_lengths

    if not instance.suitable:
        instance.suitable = suitable_lengths(instance.template)
        PoolTemplate.objects.filter(pk=instance.pk).update(suitable=instance.suitable)
    lo, hi = instance.allowed_range()
    bad = [dict(x, reason=tmsg(x["reason"])) for x in incompatible() if x["pool_pk"] == instance.pk]
    errors = [tmsg(e) for e in errors]
    draft = request.session.pop(f"isc_pool_draft_{instance.pk}", None)
    if draft:
        draft["problems"] = [(tmsg(e), n, pfx) for e, n, pfx in draft["problems"]]
    from .compat import overrides as _ovr

    own = [o for o in _ovr() if o["obj"].pool_id == instance.pk]
    chosen_override = next((o["obj"] for o in own if chosen is not None and o["obj"].prefix_id == chosen.pk and o["state"] == "active"), None)
    if chosen_override is not None:
        from .compat import _render_args

        a = _render_args()
        text, errors = render_subnet(chosen_override.code, str(chosen.prefix), a["dns"], {"obj": chosen, "cf": chosen.custom_field_data or {}},
                                     gateway_mode=a["gateway_mode"], snippets=a["snippets"], site=a["site"], known_classes=a["known_classes"], invalid=a["invalid"])
        errors = [tmsg(e) for e in errors]
    from .hosts.classes import literal_lines

    return {"prefixes": prefixes, "chosen": chosen, "rendered": text, "errors": errors, "editor_vars": _editor_vars() + _editor_classes(), "draft": draft,
            "class_hints": literal_lines(instance.template),
            "overrides": own, "chosen_override": chosen_override,
            "suitable_text": ranges_text(instance.suitable), "allowed": (lo, hi), "incompatible": bad,
            "lengths": instance.suitable}


def _check_pool_code(instance, code, lo=None, hi=None):
    """Render the code on EVERY prefix of the pool. Returns (checked prefixes, [(prefix, error), ...])."""
    from .models import DNSServer
    from .services import variable_snippets
    from .source_fields import _field_q
    from .subnet_render import render_subnet

    cfg = SubnetConfig.objects.first()
    model, qs, key = _pool_info(cfg) if cfg else (None, None, None)
    value = next((v for v, l in _pool_names(model, qs, key) if l == instance.name), None) if key is not None else None
    if value is None:
        return 0, []
    from .services import check_context

    dns = list(DNSServer.objects.filter(active=True).values_list("ip", flat=True))
    snippets, problems, n, ctx = variable_snippets(), [], 0, check_context()
    own = set(instance.overrides.values_list("prefix_id", flat=True)) if instance.allow_override else set()
    for obj in qs.filter(_field_q(model, key["field"], [value]))[:5000]:
        if obj.pk in own:
            continue  # individual code: not affected by the pool code
        plen = getattr(getattr(obj, "prefix", None), "prefixlen", None)
        if lo is not None and (plen is None or not lo <= plen <= hi):
            continue  # outside the pool's range: not exported, shown as incompatible
        n += 1
        _, errs = render_subnet(code, str(getattr(obj, "prefix", "")), dns, {"obj": obj, "cf": getattr(obj, "custom_field_data", {}) or {}},
                                gateway_mode=cfg.gateway_mode, snippets=snippets, **ctx)
        problems += [(str(obj.prefix), e) for e in errs]
    return n, problems


class PoolTemplateInlineView(View):
    def post(self, request, pk):
        if not request.user.has_perm("netbox_isc_dhcp.change_pooltemplate"):
            raise PermissionDenied
        obj = get_object_or_404(PoolTemplate, pk=pk)
        field = request.POST.get("field")
        draft_key = f"isc_pool_draft_{obj.pk}"
        if field == "to_use":  # hand-written members-of lines of dynamic classes -> USE ALLOW/DENY (same CFG)
            from .hosts.classes import to_use

            obj.template = to_use(obj.template)
            obj.save()
            messages.success(request, t("msg.saved"))
            url = obj.get_absolute_url()
            p = request.POST.get("p", "")
            return redirect(f"{url}?p={p}" if p.isdigit() else url)
        if field == "template":
            from .variables import normalize

            from .compat import suitable_lengths

            code = normalize(request.POST.get("value", ""))
            suitable = suitable_lengths(code)
            lo = max(obj.min_prefixlen or 0, min(suitable)) if suitable else None
            hi = min(obj.max_prefixlen or 99, max(suitable)) if suitable else None
            checked, problems = _check_pool_code(obj, code, lo, hi) if suitable else _check_pool_code(obj, code)
            if problems:
                # refuse: the working code stays, the edited text is kept for fixing
                grouped = {}
                for pfx, e in problems:  # same error on many prefixes -> one line
                    g = grouped.setdefault(e, [0, pfx])
                    g[0] += 1
                request.session[draft_key] = {"code": code, "problems": [(e, n, pfx) for e, (n, pfx) in list(grouped.items())[:20]],
                                              "count": len(grouped), "prefixes": len({p for p, _ in problems}), "checked": checked}
                messages.error(request, t("err.code_refused", n=len({p for p, _ in problems}), total=checked))
                url = obj.get_absolute_url()
                p = request.POST.get("p", "")
                return redirect(f"{url}?p={p}" if p.isdigit() else url)
            request.session.pop(draft_key, None)
            obj.template = code
            obj.suitable = suitable
            if obj.min_prefixlen and obj.min_prefixlen not in suitable:
                obj.min_prefixlen = None
            if obj.max_prefixlen and obj.max_prefixlen not in suitable:
                obj.max_prefixlen = None
            obj.save()
            messages.success(request, t("msg.code_saved", n=checked))
            own = list(obj.overrides.values_list("prefix_text", flat=True)) if obj.allow_override else []
            if own:
                messages.warning(request, t("msg.override_kept", list=", ".join(own[:10]) + (" …" if len(own) > 10 else "")))
            url = obj.get_absolute_url()
            p = request.POST.get("p", "")
            return redirect(f"{url}?p={p}" if p.isdigit() else url)
        elif field == "enabled":
            obj.enabled = request.POST.get("value") == "1"
            nxt = request.POST.get("next", "")
            if nxt.startswith("/plugins/isc-dhcp/"):
                obj.save()
                messages.success(request, t("msg.saved"))
                return redirect(nxt)
        elif field == "include":
            obj.include = request.POST.get("value") == "1"
            obj.save()
            nxt = request.POST.get("next", "")
            return redirect(nxt if nxt.startswith("/plugins/isc-dhcp/") else obj.get_absolute_url())
        elif field == "allow_override":
            obj.allow_override = request.POST.get("value") == "1"
        elif field == "range":
            lo, hi = request.POST.get("min", ""), request.POST.get("max", "")
            lo, hi = (int(lo) if lo.isdigit() else None), (int(hi) if hi.isdigit() else None)
            if (lo and lo not in obj.suitable) or (hi and hi not in obj.suitable) or (lo and hi and lo > hi):
                messages.error(request, t("err.range_bad"))
                return redirect(obj.get_absolute_url())
            obj.min_prefixlen, obj.max_prefixlen = lo, hi
        obj.save()
        messages.success(request, t("msg.saved"))
        url = obj.get_absolute_url()
        p = request.POST.get("p", "")
        return redirect(f"{url}?p={p}" if p.isdigit() else url)


_crud(PoolTemplate, forms.PoolTemplateForm, tables.PoolTemplateTable, inline_only=True,
      extra_context=lambda request, instance: _pooltemplate_context(request, instance))



# --- Own variables (ISC options catalog) --------------------------------------------
def _editor_vars():
    """Variables for the `..` autocomplete in code editors: [{name, lines}]."""
    from .services import variable_snippets

    return [{"name": n, "lines": l} for n, l in sorted(variable_snippets().items())]


def _editor_classes():
    """Dynamic classes for the `..` autocomplete in subnet code editors: allow + deny line per class."""
    from .services import dynamic_classes

    out = []
    for c in sorted(dynamic_classes(), key=str.lower):
        out += [{"name": c, "cls": "ALLOW", "lines": f'allow members of "{c}";'}, {"name": c, "cls": "DENY", "lines": f'deny members of "{c}";'}]
    return out


class VariablesView(LoginRequiredMixin, View):
    def get(self, request):
        from django.shortcuts import render

        from .models import ConfigVariable, DNSServer
        from .services import variable_usage
        from .variables import CATALOG, VariableError

        usage = variable_usage()
        rows = []
        for v in ConfigVariable.objects.all():
            label, group, kind, _ = CATALOG.get(v.option, (v.option, "", "raw", ""))
            label = t("opt.raw") if v.option == "raw" else label
            try:
                lines, err = v.lines(), ""
            except VariableError as exc:
                lines, err = "", tmsg(str(exc))
            rows.append({"obj": v, "label": label, "kind": kind, "lines": lines, "error": err,
                         "used_by": usage.get(v.name, []), "dns_ids": set(v.dns_servers or []),
                         "lease_def": (v.value or "").split()[0] if kind == "lease" and (v.value or "").split() else "",
                         "lease_max": (v.value or "").split()[1] if kind == "lease" and len((v.value or "").split()) > 1 else ""})
        groups = {}
        for key, (label, group, kind, _) in CATALOG.items():
            groups.setdefault(t(f"grp.{group}"), []).append((key, t("opt.raw") if key == "raw" else label, kind))
        st = PluginSettings.objects.first()
        return render(request, "netbox_isc_dhcp/variables.html", {
            "rows": rows, "catalog_groups": groups, "dns_all": DNSServer.objects.all(),
            "lease_factor": st.lease_factor if st else 1.3,
            "unknown": sorted((n, w) for n, w in usage.items() if n not in {r["obj"].name for r in rows}),
        })


def _apply_value(obj, post):
    """Set the value of a variable from the form, by the kind of its ISC option."""
    from .variables import kind_of

    kind = kind_of(obj.option)
    if kind == "dns":
        obj.dns_servers = [int(x) for x in post.getlist("dns") if x.isdigit()]
    elif kind == "raw":
        obj.value = post.get("value_raw", post.get("value", ""))
    elif kind in ("allowdeny", "truefalse", "onoff"):
        obj.value = post.get(f"value_{kind}", post.get("value", "")).strip()
    elif kind == "lease" and "value_lease_def" in post:  # default + max (seconds) or factor (e.g. 1.5)
        obj.value = " ".join(x for x in (post.get("value_lease_def", "").strip(), post.get("value_lease_max", "").strip().replace(",", ".")) if x)
    else:
        obj.value = post.get("value_text", post.get("value", "")).strip()


def _rewrite_use(old, new):
    """Rewrite every `USE old` line to `USE new` in pools, group files and subnet overrides; returns where."""
    from .models import DHCPFile, PoolTemplate, SubnetOverride
    from .variables import rename_use, used_names

    changed = []
    for pt in PoolTemplate.objects.all():
        if old in used_names(pt.template):
            pt.template = rename_use(pt.template, old, new)
            pt.save()
            changed.append(f"pool {pt.name}")
    for f in DHCPFile.objects.all():
        if old in used_names(f.template):
            f.template = rename_use(f.template, old, new)
            f.save()  # regenerates the stored file
            changed.append(f"file {f.name}")
    for o in SubnetOverride.objects.select_related("pool"):
        if old in used_names(o.code):
            o.code = rename_use(o.code, old, new)
            o.save()
            changed.append(f"subnet {o.prefix_text} ({o.pool.name})")
    return changed


class VariablesInlineView(LoginRequiredMixin, View):
    def post(self, request):
        from .models import ConfigVariable
        from .services import variable_usage
        from .variables import CATALOG, NAME_RE

        if not request.user.has_perm("netbox_isc_dhcp.change_configvariable"):
            raise PermissionDenied
        action, value = request.POST.get("field"), request.POST.get("value", "").strip()
        pk = request.POST.get("pk", "")
        obj = ConfigVariable.objects.filter(pk=int(pk)).first() if pk.isdigit() else None
        used = obj is not None and obj.name in variable_usage()
        err = ""
        if action == "add":
            from .variables import VariableError

            option = request.POST.get("option", "")
            if option not in CATALOG:
                err = t("err.var_option")
            elif not NAME_RE.match(value):
                err = t("err.var_name")
            elif ConfigVariable.objects.filter(name=value).exists():
                err = t("err.var_exists", name=value)
            else:
                new = ConfigVariable(name=value, option=option)
                _apply_value(new, request.POST)
                try:
                    new.lines()  # value is set right at creation and must be valid
                    new.save()
                except VariableError as exc:
                    err = tmsg(str(exc))
        elif obj is not None and action == "rename":
            if not NAME_RE.match(value):
                err = t("err.var_name")
            elif ConfigVariable.objects.filter(name=value).exclude(pk=obj.pk).exists():
                err = t("err.var_exists", name=value)
            elif value != obj.name:
                from django.db import transaction

                old = obj.name
                with transaction.atomic():  # name and every USE line change together
                    obj.name = value
                    obj.save()
                    changed = _rewrite_use(old, value)
                if changed:
                    messages.success(request, t("msg.var_renamed", old=old, new=value, where=", ".join(changed)))
                    return redirect("plugins:netbox_isc_dhcp:variables")
        elif action == "remap":  # repair: USE lines naming a variable that does not exist -> an existing one
            from django.db import transaction

            old = request.POST.get("old", "").strip()
            if not ConfigVariable.objects.filter(name=value).exists() or not old or ConfigVariable.objects.filter(name=old).exists():
                err = t("err.var_remap")
            else:
                with transaction.atomic():
                    changed = _rewrite_use(old, value)
                messages.success(request, t("msg.var_renamed", old=old, new=value, where=", ".join(changed) or "-"))
                return redirect("plugins:netbox_isc_dhcp:variables")
        elif obj is not None and action == "set_value":
            from .variables import VariableError

            _apply_value(obj, request.POST)
            try:
                obj.lines()
            except VariableError as exc:
                err = tmsg(str(exc))
            if not err:
                obj.save()
        elif obj is not None and action == "delete":
            if used:
                err = t("err.var_used", name=obj.name)
            else:
                obj.delete()
        elif action == "factor":
            try:
                f = float(value.replace(",", "."))
                if not 1 <= f <= 10:
                    raise ValueError
                st = PluginSettings.objects.first() or PluginSettings.objects.create()
                st.lease_factor = f
                st.save()
            except ValueError:
                err = t("err.var_factor")
        if err:
            messages.error(request, err)
        else:
            messages.success(request, t("msg.saved"))
        return redirect("plugins:netbox_isc_dhcp:variables")



# --- Individual code of one subnet (exception from its pool's code) -----------------
class SubnetOverrideView(LoginRequiredMixin, View):
    template = "netbox_isc_dhcp/override.html"

    def _objs(self, pk, prefix_pk):
        from ipam.models import Prefix

        from .models import SubnetOverride

        pool = get_object_or_404(PoolTemplate, pk=pk)
        prefix = get_object_or_404(Prefix, pk=prefix_pk)
        return pool, prefix, SubnetOverride.objects.filter(pool=pool, prefix_id=prefix.pk).first()

    def _check(self, code, prefix):
        from .compat import _render_args
        from .subnet_render import render_subnet

        a = _render_args()
        return render_subnet(code, str(prefix.prefix), a["dns"], {"obj": prefix, "cf": prefix.custom_field_data or {}},
                             gateway_mode=a["gateway_mode"], snippets=a["snippets"], site=a["site"], known_classes=a["known_classes"], invalid=a["invalid"])

    def get(self, request, pk, prefix_pk):
        from django.shortcuts import render

        pool, prefix, ovr = self._objs(pk, prefix_pk)
        draft = request.session.pop(f"isc_ovr_draft_{pool.pk}_{prefix.pk}", None)
        code = draft if draft is not None else (ovr.code if ovr else pool.template)
        text, errors = self._check(code, prefix)
        return render(request, self.template, {
            "pool": pool, "prefix": prefix, "override": ovr, "code": code, "rendered": text,
            "errors": [tmsg(e) for e in errors], "editor_vars": _editor_vars() + _editor_classes(), "draft": draft is not None,
            "class_hints": __import__("netbox_isc_dhcp.hosts.classes", fromlist=["x"]).literal_lines(ovr.code) if ovr else [],
        })

    def post(self, request, pk, prefix_pk):
        from .models import SubnetOverride
        from .variables import normalize

        if not request.user.has_perm("netbox_isc_dhcp.change_pooltemplate"):
            raise PermissionDenied
        pool, prefix, ovr = self._objs(pk, prefix_pk)
        here = request.path
        if request.POST.get("field") == "delete":
            if ovr:
                ovr.delete()
            messages.success(request, t("msg.override_removed", prefix=str(prefix.prefix)))
            return redirect(f"{pool.get_absolute_url()}?p={prefix.pk}")
        if request.POST.get("field") == "to_use" and ovr:
            from .hosts.classes import to_use

            ovr.code = to_use(ovr.code)
            ovr.save()
            messages.success(request, t("msg.saved"))
            return redirect(here)
        if not pool.allow_override:
            messages.error(request, t("err.override_off"))
            return redirect(here)
        code = normalize(request.POST.get("value", ""))
        _, errors = self._check(code, prefix)
        if errors:
            request.session[f"isc_ovr_draft_{pool.pk}_{prefix.pk}"] = code
            messages.error(request, t("err.override_refused"))
            return redirect(here)
        SubnetOverride.objects.update_or_create(pool=pool, prefix_id=prefix.pk, defaults={"prefix_text": str(prefix.prefix), "code": code})
        messages.success(request, t("msg.override_saved", prefix=str(prefix.prefix)))
        return redirect(here)



class VariablesJSONView(LoginRequiredMixin, View):
    """Current variables for the `..` autocomplete (fetched each time, so new ones appear without reload)."""

    def get(self, request):
        from django.http import JsonResponse

        return JsonResponse({"vars": _editor_vars() + (_editor_classes() if request.GET.get("classes") else [])})


def manual_pdf(request):
    """The manual (PDF) in the plugin language: Slovak NAVOD_SK.pdf or English MANUAL_EN.pdf."""
    import os

    from django.http import FileResponse, Http404

    from .i18n import current_language

    if not request.user.is_authenticated:
        raise PermissionDenied
    name = "NAVOD_SK.pdf" if current_language() == "sk" else "MANUAL_EN.pdf"
    path = os.path.join(os.path.dirname(__file__), "manual", name)
    if not os.path.exists(path):
        raise Http404
    return FileResponse(open(path, "rb"), content_type="application/pdf", filename=name)
