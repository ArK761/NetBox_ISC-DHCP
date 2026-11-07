import django_tables2 as tables
from netbox.tables import NetBoxTable, columns

from .i18n import t_lazy
from .models import BaseConfig, DHCPGroup, DNSServer, PluginSettings


class BaseConfigTable(NetBoxTable):
    name = tables.Column(linkify=True)

    class Meta(NetBoxTable.Meta):
        model = BaseConfig
        fields = ("pk", "id", "name", "table_dir", "subnet_dir", "prefix_field", "prefix_value")
        default_columns = ("name", "table_dir", "subnet_dir")


class DHCPGroupTable(NetBoxTable):
    group = tables.Column(linkify=True)

    class Meta(NetBoxTable.Meta):
        model = DHCPGroup
        fields = ("pk", "id", "group", "order")
        default_columns = ("group", "order")


TOGGLE = """<form method="post" action="{% url 'plugins:netbox_isc_dhcp:dnsserver_toggle' pk=record.pk %}" class="d-inline">
{% csrf_token %}<button type="submit" class="btn btn-link p-0 border-0"><i class="mdi {% if record.active %}mdi-checkbox-marked text-success{% else %}mdi-checkbox-blank-outline text-muted{% endif %} fs-3"></i></button></form>"""


class DNSServerTable(NetBoxTable):
    name = tables.Column(linkify=True, verbose_name=t_lazy("col.name"))
    active = tables.TemplateColumn(template_code=TOGGLE, verbose_name=t_lazy("col.in_use"), orderable=False)

    class Meta(NetBoxTable.Meta):
        model = DNSServer
        fields = ("pk", "id", "name", "ip", "active")
        default_columns = ("name", "ip", "active")


class PluginSettingsTable(NetBoxTable):
    language = tables.Column(linkify=True)

    class Meta(NetBoxTable.Meta):
        model = PluginSettings
        fields = ("pk", "id", "language")
        default_columns = ("language",)
