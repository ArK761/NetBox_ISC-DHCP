from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.views import View
from netbox.views import generic
from utilities.views import ViewTab, register_model_view

from . import forms, tables
from .i18n import t, t_lazy
from .models import MAX_ACTIVE_DNS, BaseConfig, DHCPGroup, DNSServer, PluginSettings
from .services import build_base_config


def _crud(model, form_cls, table_cls):
    """Register list / detail / add / edit / delete views for a model."""

    @register_model_view(model, "list", path="", detail=False)
    class ListView(generic.ObjectListView):
        queryset = model.objects.all()
        table = table_cls

    @register_model_view(model)
    class DetailView(generic.ObjectView):
        queryset = model.objects.all()
        template_name = f"netbox_isc_dhcp/{model._meta.model_name}.html"

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
_crud(BaseConfig, forms.BaseConfigForm, tables.BaseConfigTable)


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


# --- Plugin settings -------------------------------------------------------------
_crud(PluginSettings, forms.PluginSettingsForm, tables.PluginSettingsTable)


# --- Singleton entry points (menu opens the one existing object) ----------------
class _OpenSingleton(View):
    model = None
    viewname = None

    def get(self, request):
        obj = self.model.objects.first() or self.model.objects.create()
        return redirect(obj.get_absolute_url())


class BaseConfigOpenView(_OpenSingleton):
    model = BaseConfig


class PluginSettingsOpenView(_OpenSingleton):
    model = PluginSettings


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
