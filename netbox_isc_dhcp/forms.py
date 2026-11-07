from netbox.forms import NetBoxModelForm

from .models import BaseConfig, DHCPGroup, DNSServer, PluginSettings


class BaseConfigForm(NetBoxModelForm):
    class Meta:
        model = BaseConfig
        fields = ("name", "static_text", "table_dir", "subnet_dir", "prefix_field", "prefix_value", "tags")


class DHCPGroupForm(NetBoxModelForm):
    class Meta:
        model = DHCPGroup
        fields = ("group", "order", "tags")


class DNSServerForm(NetBoxModelForm):
    class Meta:
        model = DNSServer
        fields = ("name", "ip", "active", "tags")


class PluginSettingsForm(NetBoxModelForm):
    class Meta:
        model = PluginSettings
        fields = ("language", "tags")
