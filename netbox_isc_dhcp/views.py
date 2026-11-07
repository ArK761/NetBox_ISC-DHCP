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
        queryset = model.objects.all()

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
    FIELDS = ("source_model", "prefix_field", "prefix_value", "static_text")

    def post(self, request, pk):
        if not request.user.has_perm("netbox_isc_dhcp.change_baseconfig"):
            raise PermissionDenied
        obj = get_object_or_404(BaseConfig, pk=pk)
        field = request.POST.get("field")
        if field in self.FIELDS:
            value = request.POST.get("value", "")
            setattr(obj, field, value if field == "static_text" else value.strip())
            try:
                obj.full_clean()
                obj.save()
                messages.success(request, t("msg.saved"))
            except ValidationError as exc:
                messages.error(request, "; ".join(m for ms in exc.message_dict.values() for m in ms))
        return redirect(obj.get_absolute_url())


def _baseconfig_context(request, instance):
    from extras.models import CustomField
    from ipam.models import Prefix

    from .models import settings_obj

    st = settings_obj()
    cfs = sorted(CustomField.objects.get_for_model(Prefix), key=lambda c: c.name)
    cur = next((c for c in cfs if c.name == instance.prefix_field), None)
    values = []
    if cur is not None:
        if cur.type == "boolean":
            values = ["true", "false"]
        elif getattr(cur, "choice_set", None):
            values = [c[0] for c in cur.choice_set.choices]
    path = f"{st.config_path.rstrip('/')}/{instance.name}" if st and st.config_path else ""
    return {"cf_choices": [(c.name, c.label or c.name) for c in cfs], "value_choices": values, "file_path": path}
