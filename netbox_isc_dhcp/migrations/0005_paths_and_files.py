import os

import django.db.models.deletion
import taggit.managers
import utilities.json
from django.db import migrations, models

import netbox_isc_dhcp.dhcp_tables


def _common():
    return [
        ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
        ("created", models.DateTimeField(auto_now_add=True, null=True)),
        ("last_updated", models.DateTimeField(auto_now=True, null=True)),
        ("custom_field_data", models.JSONField(blank=True, default=dict, encoder=utilities.json.CustomFieldJSONEncoder)),
    ]


def _tags():
    return ("tags", taggit.managers.TaggableManager(through="extras.TaggedItem", to="extras.Tag"))


def move_data(apps, schema_editor):
    """Old layout: one table_dir/subnet_dir and two templates per group -> directories and one file each."""
    BaseConfig = apps.get_model("netbox_isc_dhcp", "BaseConfig")
    DHCPPath = apps.get_model("netbox_isc_dhcp", "DHCPPath")
    DHCPGroup = apps.get_model("netbox_isc_dhcp", "DHCPGroup")
    DHCPFile = apps.get_model("netbox_isc_dhcp", "DHCPFile")
    for cfg in BaseConfig.objects.all():
        cfg.base_path = os.path.dirname(cfg.table_dir.rstrip("/")) or "/opt/dhcp"
        cfg.save(update_fields=["base_path"])
    table, _ = DHCPPath.objects.get_or_create(name="TABLE", defaults={"order": 10})
    DHCPPath.objects.get_or_create(name="SUBNET", defaults={"order": 20})
    for g in DHCPGroup.objects.select_related("group"):
        for suffix, order, tpl in (("_Table", 10, g.table_template), ("_StaticTable", 20, g.static_template)):
            DHCPFile.objects.get_or_create(
                group=g, directory=table, name=f"{g.group.name}{suffix}",
                defaults={"order": order, "template": tpl, "mac_fields": g.mac_fields, "ip_field": g.ip_field},
            )


class Migration(migrations.Migration):
    dependencies = [
        ("extras", "__latest__"),
        ("netbox_isc_dhcp", "0004_dhcpgroup_tables"),
    ]

    operations = [
        migrations.CreateModel(
            name="DHCPPath",
            fields=_common() + [
                ("name", models.CharField(max_length=50, unique=True)),
                ("order", models.PositiveSmallIntegerField(default=100)),
                _tags(),
            ],
            options={"ordering": ("order", "name"), "verbose_name": "directory"},
        ),
        migrations.CreateModel(
            name="DHCPFile",
            fields=_common() + [
                ("name", models.CharField(help_text="File name, e.g. WorkStation_Table.", max_length=100)),
                ("enabled", models.BooleanField(default=True, verbose_name="Include in dhcpd.conf")),
                ("order", models.PositiveSmallIntegerField(default=100)),
                ("mac_fields", models.JSONField(blank=True, default=list, help_text="Tenant custom fields that hold a MAC address.")),
                ("ip_field", models.CharField(blank=True, help_text="Tenant custom field with the static IP (optional).", max_length=100)),
                ("template", models.TextField(blank=True, default=netbox_isc_dhcp.dhcp_tables.default_table_template, help_text="Jinja template: how the file looks.")),
                ("directory", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="files", to="netbox_isc_dhcp.dhcppath")),
                ("group", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="files", to="netbox_isc_dhcp.dhcpgroup")),
                _tags(),
            ],
            options={"ordering": ("order", "name")},
        ),
        migrations.AddConstraint(
            model_name="dhcpfile",
            constraint=models.UniqueConstraint(fields=("directory", "name"), name="netbox_isc_dhcp_file_unique"),
        ),
        migrations.AddField(
            model_name="baseconfig", name="config_path",
            field=models.CharField(default="/etc/dhcp", help_text="Directory of dhcpd.conf on the DHCP server.", max_length=255),
        ),
        migrations.AddField(
            model_name="baseconfig", name="base_path",
            field=models.CharField(default="/opt/dhcp", help_text="Base directory of all other DHCP files; directories (TABLE, SUBNET...) live below it.", max_length=255),
        ),
        migrations.RunPython(move_data, migrations.RunPython.noop),
        migrations.RemoveField(model_name="baseconfig", name="table_dir"),
        migrations.RemoveField(model_name="baseconfig", name="subnet_dir"),
        migrations.RemoveField(model_name="dhcpgroup", name="mac_fields"),
        migrations.RemoveField(model_name="dhcpgroup", name="ip_field"),
        migrations.RemoveField(model_name="dhcpgroup", name="table_template"),
        migrations.RemoveField(model_name="dhcpgroup", name="static_template"),
    ]
