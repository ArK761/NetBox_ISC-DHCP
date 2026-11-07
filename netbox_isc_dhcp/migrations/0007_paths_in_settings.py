from django.db import migrations, models


def copy_paths(apps, schema_editor):
    BaseConfig = apps.get_model("netbox_isc_dhcp", "BaseConfig")
    PluginSettings = apps.get_model("netbox_isc_dhcp", "PluginSettings")
    cfg = BaseConfig.objects.first()
    st = PluginSettings.objects.first() or PluginSettings.objects.create()
    if cfg:
        st.config_path, st.base_path = cfg.config_path, cfg.base_path
        st.save(update_fields=["config_path", "base_path"])


class Migration(migrations.Migration):
    dependencies = [("netbox_isc_dhcp", "0006_dhcpfile_stored_content")]

    operations = [
        migrations.AddField(
            model_name="pluginsettings", name="config_path",
            field=models.CharField(default="/etc/dhcp", help_text="Directory of dhcpd.conf on the DHCP server.", max_length=255),
        ),
        migrations.AddField(
            model_name="pluginsettings", name="base_path",
            field=models.CharField(default="/opt/dhcp", help_text="Base directory of all other DHCP files; subdirectories (TABLE, SUBNET...) live below it.", max_length=255),
        ),
        migrations.RunPython(copy_paths, migrations.RunPython.noop),
        migrations.RemoveField(model_name="baseconfig", name="config_path"),
        migrations.RemoveField(model_name="baseconfig", name="base_path"),
    ]
