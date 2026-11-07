from django.db import migrations, models


def clear_defaults(apps, schema_editor):
    PluginSettings = apps.get_model("netbox_isc_dhcp", "PluginSettings")
    PluginSettings.objects.filter(config_path="/etc/dhcp").update(config_path="")
    PluginSettings.objects.filter(base_path="/opt/dhcp").update(base_path="")


class Migration(migrations.Migration):
    dependencies = [("netbox_isc_dhcp", "0008_subdirs_empty_by_default")]

    operations = [
        migrations.AlterField(model_name="pluginsettings", name="config_path",
            field=models.CharField(blank=True, default="", help_text="Directory of dhcpd.conf on the DHCP server.", max_length=255)),
        migrations.AlterField(model_name="pluginsettings", name="base_path",
            field=models.CharField(blank=True, default="", help_text="Base directory of all other DHCP files; subdirectories (TABLE, SUBNET...) live below it.", max_length=255)),
        migrations.RunPython(clear_defaults, migrations.RunPython.noop),
    ]
