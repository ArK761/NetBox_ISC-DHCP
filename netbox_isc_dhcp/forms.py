from django import forms
from extras.models import CustomField
from netbox.forms import NetBoxModelForm as _NetBoxModelForm


class NetBoxModelForm(_NetBoxModelForm):
    """No tags in this plugin."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name in ("tags", "changelog_message"):  # no tags, no changelog in this plugin
            self.fields.pop(name, None)

from tenancy.models import Tenant

from .models import BaseConfig, DHCPFile, DHCPGroup, DHCPPath, DNSServer, PluginSettings


class BaseConfigForm(NetBoxModelForm):
    class Meta:
        model = BaseConfig
        fields = ("name", "static_text", "source_model")
        widgets = {"static_text": forms.Textarea(attrs={"rows": 24, "style": "font-family:monospace"})}


class DHCPPathForm(NetBoxModelForm):
    class Meta:
        model = DHCPPath
        fields = ("name", "order")


class DHCPGroupForm(NetBoxModelForm):
    class Meta:
        model = DHCPGroup
        fields = ("group", "enabled", "order")
        labels = {"enabled": "Include in dhcpd.conf"}


class DHCPFileForm(NetBoxModelForm):
    mac_fields = forms.MultipleChoiceField(
        required=False, widget=forms.CheckboxSelectMultiple, label="MAC fields (tick the tenant fields with a MAC)"
    )
    ip_field = forms.ChoiceField(required=False, label="Static IP field")

    class Meta:
        model = DHCPFile
        fields = ("group", "name", "directory", "enabled", "order", "mac_fields", "ip_field", "template")
        widgets = {"template": forms.Textarea(attrs={"rows": 24, "style": "font-family:monospace"})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        cfs = sorted(CustomField.objects.get_for_model(Tenant), key=lambda cf: cf.name)
        choices = [(cf.name, f"{cf.label or cf.name} ({cf.name})") for cf in cfs]
        self.fields["mac_fields"].choices = choices
        self.fields["ip_field"].choices = [("", "- none -")] + choices


class DNSServerForm(NetBoxModelForm):
    class Meta:
        model = DNSServer
        fields = ("name", "ip", "active")


class PluginSettingsForm(NetBoxModelForm):
    class Meta:
        model = PluginSettings
        fields = ("language", "config_path", "base_path", "table_dir", "subnet_dir")
