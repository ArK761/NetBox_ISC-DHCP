import django.db.models.deletion
from django.db import migrations, models


def to_sources(apps, schema_editor):
    """The old single host source of a group becomes one dynamic and one static source; the link to the
    group becomes a condition (link field = this group)."""
    HostGroup = apps.get_model("netbox_isc_dhcp", "HostGroup")
    HostSource = apps.get_model("netbox_isc_dhcp", "HostSource")
    for g in HostGroup.objects.exclude(mac_model=""):
        link = g.link_field or ("group" if g.mac_model == "tenancy.tenant" and g.group_model == "tenancy.tenantgroup" else "")
        conds = [{"field": link, "values": [str(g.group_pk)], "mode": "include"}] if link else []
        for kind in ("dynamic", "static"):
            HostSource.objects.create(group=g, kind=kind, model=g.mac_model, conditions=conds, host_name_field=g.host_name_field or "name",
                                      mac_fields=list(g.mac_fields or []), ip_field=g.ip_field)


class Migration(migrations.Migration):

    dependencies = [
        ("netbox_isc_dhcp", "0022_hostgroup_enabled"),
    ]

    operations = [
        migrations.AddField(model_name="hostgroup", name="dynamic_suffix",
                            field=models.CharField(default="_Dynamic", help_text="File name = group name + this suffix (hosts without IP).", max_length=50)),
        migrations.AddField(model_name="hostgroup", name="static_suffix",
                            field=models.CharField(default="_Static", help_text="File name = group name + this suffix (hosts with static IP).", max_length=50)),
        migrations.CreateModel(
            name="HostSource",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ("kind", models.CharField(choices=[("dynamic", "dynamic"), ("static", "static")], max_length=10)),
                ("order", models.PositiveSmallIntegerField(default=100)),
                ("model", models.CharField(blank=True, default="", help_text="Object type of the hosts, e.g. tenancy.tenant or dcim.device.", max_length=100)),
                ("conditions", models.JSONField(blank=True, default=list, help_text="Conditions [{field, values, mode include|exclude}] choosing the objects.")),
                ("host_name_field", models.CharField(blank=True, default="name", max_length=100)),
                ("mac_fields", models.JSONField(blank=True, default=list, help_text="Fields with MAC addresses (1-3), in order.")),
                ("ip_field", models.CharField(blank=True, default="", help_text="Static file: field with the static IP. Dynamic file: objects with a value in this field are left out.", max_length=100)),
                ("group", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="sources", to="netbox_isc_dhcp.hostgroup")),
            ],
            options={"verbose_name": "host source", "ordering": ("group", "kind", "order", "pk")},
        ),
        migrations.RunPython(to_sources, migrations.RunPython.noop),
        migrations.RemoveField(model_name="hostgroup", name="mac_model"),
        migrations.RemoveField(model_name="hostgroup", name="link_field"),
        migrations.RemoveField(model_name="hostgroup", name="host_name_field"),
        migrations.RemoveField(model_name="hostgroup", name="mac_fields"),
        migrations.RemoveField(model_name="hostgroup", name="ip_field"),
    ]
