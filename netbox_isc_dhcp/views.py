from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
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


# --- Plugin settings: language, dhcpd.conf path, base path and subdirectories ---
_crud(PluginSettings, forms.PluginSettingsForm, tables.PluginSettingsTable, singleton=True,
      extra_context=lambda request, instance: {
          "subdirs": DHCPPath.objects.all(),
          "dir_rows": [("table_dir", "lbl.table_dir", instance.table_dir), ("subnet_dir", "lbl.subnet_dir2", instance.subnet_dir)],
          "path_rows": [
              ("config_path", "lbl.config_path", instance.config_path, "/etc/dhcp"),
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
    FIELDS = ("language", "config_path", "base_path", "table_dir", "subnet_dir")

    def post(self, request, pk):
        if not request.user.has_perm("netbox_isc_dhcp.change_pluginsettings"):
            raise PermissionDenied
        obj = get_object_or_404(PluginSettings, pk=pk)
        field = request.POST.get("field")
        if field in self.FIELDS:
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
        elif action == "subnet_dir":
            from .models import settings_obj

            st = settings_obj() or PluginSettings.objects.create()
            st.subnet_dir_id = int(value) if value.isdigit() and DHCPPath.objects.filter(pk=int(value)).exists() else None
            st.save()
        elif row is not None and action == "cond_poolkey" and len(distinct_values(model, row["field"])) > MAX_POOLS:
            messages.error(request, t("err.pool_key_many", n=len(distinct_values(model, row["field"])), max=MAX_POOLS))
            return redirect(obj.get_absolute_url())
        elif row is not None and action == "cond_poolkey":
            for c in conds:
                c["pool_key"] = False
            row["pool_key"] = True
        elif row is not None and action == "cond_del":
            conds.pop(idx)
        obj.conditions = conds
        obj.save()
        messages.success(request, t("msg.saved"))
        return redirect(obj.get_absolute_url())


def _baseconfig_context(request, instance):
    from .models import settings_obj
    from .services import table_includes

    st = settings_obj()
    includes, warnings = table_includes()
    path = f"{st.config_path.rstrip('/')}/{instance.name}" if st and st.config_path else ""
    return {"file_path": path, "includes": includes, "include_warnings": warnings}


# --- DHCP-CFG hub: the menu item that leads to all DHCP configuration parts ------
class DHCPHubView(LoginRequiredMixin, View):
    def get(self, request):
        from django.shortcuts import render

        items = [
            ("plugins:netbox_isc_dhcp:baseconfig_list", "mdi-file-cog-outline", "menu.base", "hub.base"),
            ("plugins:netbox_isc_dhcp:dnsserver_list", "mdi-dns-outline", "menu.dns", "hub.dns"),
            ("plugins:netbox_isc_dhcp:subnetconfig_list", "mdi-ip-network-outline", "menu.subnets", "hub.subnets"),
            ("plugins:netbox_isc_dhcp:dhcpgroup_list", "mdi-lan-connect", "menu.hosts", "hub.hosts"),
            ("plugins:netbox_isc_dhcp:variables", "mdi-variable", "menu.vars", "hub.vars"),
        ]
        return render(request, "netbox_isc_dhcp/dhcp_hub.html", {"items": items})


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


def _pool_names(model, qs, key) -> list[tuple[str, str]]:
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
        can_key = not c.get("pool_key") and len(options or distinct_values(model, c.get("field"))) <= MAX_POOLS
        rows.append({"index": i, "key": c.get("field"), "label": label_for(model, c.get("field")), "values": set(vals), "mode": mode,
                     "pool_key": bool(c.get("pool_key")), "summary": summary, "options": options if is_open else [], "open": is_open,
                     "can_key": can_key})
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
            for value, name in names:
                pt, _ = PoolTemplate.objects.get_or_create(name=name[:100])
                lo, hi = pt.allowed_range()
                pools.append({"obj": pt, "count": qs.filter(_field_q(model, key["field"], [value])).count(),
                              "range": f"/{lo} – /{hi}" if lo else "—", "bad": sum(1 for x in bad if x["pool_pk"] == pt.pk),
                              "ovr": ovr.get(pt.pk, 0)})
    return {"source_groups": groups, "source_label": source_label(instance.source_model), "field_options": field_options(model),
            "cond_rows": rows, "matched_count": count, "has_pool_key": key is not None, "pools": pools, "pools_error": pools_error,
            "incompatible": [dict(x, reason=tmsg(x["reason"])) for x in __import__("netbox_isc_dhcp.compat", fromlist=["x"]).incompatible()] if key is not None and any_active else [],
            "overrides": __import__("netbox_isc_dhcp.compat", fromlist=["x"]).overrides(),
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
    return {"prefixes": prefixes, "chosen": chosen, "rendered": text, "errors": errors, "editor_vars": _editor_vars(), "draft": draft,
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
                         "used_by": usage.get(v.name, []), "dns_ids": set(v.dns_servers or [])})
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
            "errors": [tmsg(e) for e in errors], "editor_vars": _editor_vars(), "draft": draft is not None,
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

        return JsonResponse({"vars": _editor_vars()})
