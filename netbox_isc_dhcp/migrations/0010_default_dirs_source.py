import django.db.models.deletion
from django.db import migrations, models


def set_defaults(apps, schema_editor):
    PluginSettings = apps.get_model("netbox_isc_dhcp", "PluginSettings")
    DHCPPath = apps.get_model("netbox_isc_dhcp", "DHCPPath")
    for st in PluginSettings.objects.all():
        st.table_dir = DHCPPath.objects.filter(name="TABLE").first()
        st.subnet_dir = DHCPPath.objects.filter(name="SUBNET").first()
        st.save(update_fields=["table_dir", "subnet_dir"])


class Migration(migrations.Migration):
    dependencies = [("netbox_isc_dhcp", "0009_paths_empty_by_default")]

    operations = [
        migrations.AddField(model_name="baseconfig", name="source_model",
            field=models.CharField(choices=[("ipam.prefix", "IPAM › Prefix")], default="ipam.prefix", help_text="Object the subnet includes are built from.", max_length=50)),
        migrations.AddField(model_name="pluginsettings", name="table_dir",
            field=models.ForeignKey(blank=True, help_text="Default subdirectory of tenant table files.", null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to="netbox_isc_dhcp.dhcppath")),
        migrations.AddField(model_name="pluginsettings", name="subnet_dir",
            field=models.ForeignKey(blank=True, help_text="Subdirectory of the subnet (prefix) files.", null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to="netbox_isc_dhcp.dhcppath")),
        migrations.RunPython(set_defaults, migrations.RunPython.noop),
    ]
