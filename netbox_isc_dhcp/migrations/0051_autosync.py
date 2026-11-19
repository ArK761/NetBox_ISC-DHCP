from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("netbox_isc_dhcp", "0050_audit_level")]

    operations = [
        migrations.AddField(model_name="pluginsettings", name="agent_autosync",
                            field=models.CharField(max_length=8, default="off", help_text="Auto CFG sync when a server runs another CFG: off | after (X minutes) | at (fixed time).")),
        migrations.AddField(model_name="pluginsettings", name="agent_autosync_min",
                            field=models.PositiveSmallIntegerField(default=15, help_text="Minutes of CFG mismatch before NetBox pushes the full CFG.")),
        migrations.AddField(model_name="pluginsettings", name="agent_autosync_at",
                            field=models.CharField(max_length=5, default="03:00", help_text="Daily time (HH:MM) of the auto CFG sync.")),
        migrations.AddField(model_name="dhcpserver", name="mismatch_since",
                            field=models.DateTimeField(null=True, blank=True, help_text="The server runs another CFG than NetBox since.")),
        migrations.AddField(model_name="dhcpserver", name="autosync_last",
                            field=models.DateTimeField(null=True, blank=True, help_text="Last automatic CFG sync pushed by NetBox.")),
    ]
