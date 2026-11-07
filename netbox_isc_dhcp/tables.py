import django_tables2 as tables
from netbox.tables import NetBoxTable, columns

from .models import BaseConfig, DHCPGroup, DNSServer


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


class DNSServerTable(NetBoxTable):
    name = tables.Column(linkify=True)
    active = columns.BooleanColumn(verbose_name="In use")

    class Meta(NetBoxTable.Meta):
        model = DNSServer
        fields = ("pk", "id", "name", "ip", "active")
        default_columns = ("name", "ip", "active")
