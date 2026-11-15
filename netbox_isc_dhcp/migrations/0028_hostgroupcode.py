import django.db.models.deletion
from django.db import migrations, models


def move(apps, schema_editor):
    G = apps.get_model("netbox_isc_dhcp", "HostGroup")
    C = apps.get_model("netbox_isc_dhcp", "HostGroupCode")
    for g in G.objects.all():
        for kind in ("dynamic", "static"):
            code = getattr(g, kind + "_code")
            if code:
                setattr(g, kind + "_local", C.objects.create(group=g, kind=kind, name="Lokálne upravený", code=code))
                setattr(g, kind + "_code", "")
        g.save()


class Migration(migrations.Migration):
    dependencies = [("netbox_isc_dhcp", "0027_hostcodetemplate")]

    operations = [
        migrations.CreateModel(
            name="HostGroupCode",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ("kind", models.CharField(choices=[("dynamic", "Dynamic"), ("static", "Static")], max_length=10)),
                ("name", models.CharField(max_length=100)),
                ("code", models.TextField(blank=True, default="")),
                ("group", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="codes", to="netbox_isc_dhcp.hostgroup")),
            ],
            options={"verbose_name": "group code", "ordering": ("kind", "name")},
        ),
        migrations.AddConstraint(model_name="hostgroupcode",
                                 constraint=models.UniqueConstraint(fields=("group", "kind", "name"), name="netbox_isc_dhcp_hostgroupcode_unique")),
        migrations.AddField(model_name="hostgroup", name="dynamic_local",
                            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to="netbox_isc_dhcp.hostgroupcode")),
        migrations.AddField(model_name="hostgroup", name="static_local",
                            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to="netbox_isc_dhcp.hostgroupcode")),
        migrations.AlterField(model_name="hostgroup", name="dynamic_code", field=models.TextField(blank=True, default="", help_text="Unused since 0028 (moved to HostGroupCode).")),
        migrations.AlterField(model_name="hostgroup", name="static_code", field=models.TextField(blank=True, default="", help_text="Unused since 0028 (moved to HostGroupCode).")),
        migrations.RunPython(move, migrations.RunPython.noop),
    ]
