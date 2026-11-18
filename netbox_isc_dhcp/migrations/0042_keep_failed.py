from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("netbox_isc_dhcp", "0041_agent_key_rotation")]

    operations = [
        migrations.AddField(model_name="pluginsettings", name="agent_keep_failed",
                            field=models.BooleanField(default=False, help_text="On a failed test the agent keeps the new CFG on disk (debugging), no restart.")),
        migrations.AddField(model_name="dhcpserver", name="disk_broken",
                            field=models.CharField(max_length=64, blank=True, default="", help_text="Failed CFG kept on disk (debugging) - dhcpd would not start after a reboot.")),
    ]
