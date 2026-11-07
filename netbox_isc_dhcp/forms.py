from django import forms
from extras.models import CustomField
from netbox.forms import NetBoxModelForm
from tenancy.models import Tenant

from .models import BaseConfig, DHCPGroup, DNSServer, PluginSettings


class BaseConfigForm(NetBoxModelForm):
    class Meta:
        model = BaseConfig
        fields = ("name", "static_text", "table_dir", "subnet_dir", "prefix_field", "prefix_value", "tags")


class DHCPGroupForm(NetBoxModelForm):
    mac_fields = forms.MultipleChoiceField(
        required=False, widget=forms.CheckboxSelectMultiple, label="MAC fields (tick the tenant fields with a MAC)"
    )
    ip_field = forms.ChoiceField(required=False, label="Static IP field")

    class Meta:
        model = DHCPGroup
        fields = ("group", "enabled", "order", "mac_fields", "ip_field", "table_template", "static_template", "tags")
        widgets = {
            "table_template": forms.Textarea(attrs={"rows": 22, "style": "font-family:monospace"}),
            "static_template": forms.Textarea(attrs={"rows": 10, "style": "font-family:monospace"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        cfs = sorted(CustomField.objects.get_for_model(Tenant), key=lambda cf: cf.name)
        choices = [(cf.name, f"{cf.label or cf.name} ({cf.name})") for cf in cfs]
        self.fields["mac_fields"].choices = choices
        self.fields["ip_field"].choices = [("", "- none (everything is dynamic) -")] + choices


class DNSServerForm(NetBoxModelForm):
    class Meta:
        model = DNSServer
        fields = ("name", "ip", "active", "tags")


class PluginSettingsForm(NetBoxModelForm):
    class Meta:
        model = PluginSettings
        fields = ("language", "tags")
