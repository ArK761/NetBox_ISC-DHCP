import django_tables2 as tables
from netbox.tables import NetBoxTable, columns

from .i18n import t_lazy
from .models import BaseConfig, DHCPFile, DHCPGroup, DHCPPath, DNSServer, PluginSettings


class BaseConfigTable(NetBoxTable):
    name = tables.Column(linkify=True)

    class Meta(NetBoxTable.Meta):
        model = BaseConfig
        fields = ("pk", "id", "name", "config_path", "base_path", "prefix_field", "prefix_value")
        default_columns = ("name", "config_path", "base_path")


class DHCPPathTable(NetBoxTable):
    name = tables.Column(linkify=True, verbose_name=t_lazy("lbl.name"))
    path = tables.Column(empty_values=(), orderable=False, verbose_name=t_lazy("lbl.path"))
    order = tables.Column(verbose_name=t_lazy("lbl.order"))

    def render_path(self, record):
        return record.path

    class Meta(NetBoxTable.Meta):
        model = DHCPPath
        fields = ("pk", "id", "name", "path", "order")
        default_columns = ("name", "path", "order")


class DHCPGroupTable(NetBoxTable):
    group = tables.Column(linkify=lambda record: record.get_absolute_url(), verbose_name=t_lazy("lbl.tenant_group"))
    enabled = columns.BooleanColumn(verbose_name=t_lazy("col.export"))
    files = tables.Column(empty_values=(), orderable=False, verbose_name=t_lazy("lbl.files"))
    order = tables.Column(verbose_name=t_lazy("lbl.order"))

    def render_files(self, record):
        return ", ".join(f.name for f in record.files.all())

    class Meta(NetBoxTable.Meta):
        model = DHCPGroup
        fields = ("pk", "id", "group", "enabled", "files", "order")
        default_columns = ("group", "enabled", "files", "order")


REGEN = """<form method="post" action="{% url 'plugins:netbox_isc_dhcp:dhcpfile_regenerate' pk=record.pk %}" class="d-inline">
{% csrf_token %}<button type="submit" class="btn btn-link p-0 border-0" title="Regenerate"><i class="mdi mdi-refresh fs-4"></i></button></form>"""


class DHCPFileTable(NetBoxTable):
    name = tables.Column(linkify=True, verbose_name=t_lazy("lbl.name"))
    directory = tables.Column(verbose_name=t_lazy("lbl.directory"))
    enabled = columns.BooleanColumn(verbose_name=t_lazy("col.include"))
    order = tables.Column(verbose_name=t_lazy("lbl.order"))
    generated = tables.DateTimeColumn(verbose_name=t_lazy("lbl.generated_at"))
    regen = tables.TemplateColumn(template_code=REGEN, verbose_name="", orderable=False)

    class Meta(NetBoxTable.Meta):
        model = DHCPFile
        fields = ("pk", "id", "name", "group", "directory", "enabled", "order", "generated", "regen")
        default_columns = ("name", "directory", "enabled", "generated", "regen")


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
