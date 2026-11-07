from netbox.views import generic
from utilities.views import ViewTab, register_model_view

from . import forms, tables
from .models import BaseConfig, DHCPGroup, DNSServer
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
    tab = ViewTab(label="Preview")

    def get_extra_context(self, request, instance):
        text, warnings = build_base_config(instance)
        return {"generated": text, "warnings": warnings}


# --- DHCP groups -----------------------------------------------------------------
_crud(DHCPGroup, forms.DHCPGroupForm, tables.DHCPGroupTable)

# --- DNS -------------------------------------------------------------------------
_crud(DNSServer, forms.DNSServerForm, tables.DNSServerTable)
