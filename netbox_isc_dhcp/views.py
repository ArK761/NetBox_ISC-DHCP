from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.shortcuts import get_object_or_404, redirect
from django.views import View
from netbox.object_actions import AddObject, BulkDelete
from netbox.views import generic
from utilities.views import ViewTab, register_model_view

from . import forms, tables
from .i18n import t, t_lazy
from .models import MAX_ACTIVE_DNS, BaseConfig, DHCPFile, DHCPGroup, DHCPPath, DNSServer, PluginSettings
from .services import build_base_config


def _crud(model, form_cls, table_cls, singleton=False, extra_context=None):
    """Register list / detail / add / edit / delete views for a model."""

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

        def get_extra_context(self, request, instance):
            return extra_context(request, instance) if extra_context else {}

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

    return ListView, DetailView, EditView, DeleteView


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
    """Click-to-edit on the dhcpd.conf page: object, conditions (field + accepted value), passive text."""

    def post(self, request, pk):
        from .source_fields import field_options, get_model

        if not request.user.has_perm("netbox_isc_dhcp.change_baseconfig"):
            raise PermissionDenied
        obj = get_object_or_404(BaseConfig, pk=pk)
        field, value = request.POST.get("field"), request.POST.get("value", "")
        conds = list(obj.conditions or [])
        idx = request.POST.get("index", "")
        idx = int(idx) if idx.isdigit() else None
        if field == "source_model":
            from .source_fields import get_model as _gm

            if value.strip() and _gm(value.strip()) is None:
                messages.error(request, "Unknown object type.")
                return redirect(obj.get_absolute_url())
            if value.strip() != obj.source_model:
                obj.conditions = []  # fields belong to the object
            obj.source_model = value.strip()
        elif field == "static_text":
            obj.static_text = value
        elif field == "cond_add":
            keys = {o["key"] for o in field_options(get_model(obj.source_model))}
            if value in keys:
                conds.append({"field": value, "value": ""})
                obj.conditions = conds
        elif field == "cond_value" and idx is not None and idx < len(conds):
            conds[idx]["value"] = value.strip()
            obj.conditions = conds
        elif field == "cond_del" and idx is not None and idx < len(conds):
            conds.pop(idx)
            obj.conditions = conds
        try:
            obj.full_clean()
            obj.save()
            messages.success(request, t("msg.saved"))
        except ValidationError as exc:
            messages.error(request, "; ".join(m for ms in exc.message_dict.values() for m in ms))
        return redirect(obj.get_absolute_url())


def _baseconfig_context(request, instance):
    from .models import settings_obj
    from .services import table_includes

    st = settings_obj()
    includes, warnings = table_includes()
    path = f"{st.config_path.rstrip('/')}/{instance.name}" if st and st.config_path else ""
    return {"file_path": path, "includes": includes, "include_warnings": warnings}
