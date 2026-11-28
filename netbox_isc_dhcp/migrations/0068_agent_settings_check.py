from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("netbox_isc_dhcp", "0067_production")]

    operations = [
        migrations.AddField(model_name="pluginsettings", name="agent_settings_check",
                            field=models.PositiveSmallIntegerField(default=5, help_text="Minutes: the agent reports the settings it really uses this often (back-check, page Nastavenia agentov).")),
        migrations.AddField(model_name="dhcpserver", name="agent_eff",
                            field=models.TextField(blank=True, default="", help_text="Settings the agent reports it really uses (back-check).")),
        migrations.AddField(model_name="dhcpserver", name="agent_eff_at",
                            field=models.DateTimeField(null=True, blank=True, help_text="When the agent last reported its settings.")),
    ]
