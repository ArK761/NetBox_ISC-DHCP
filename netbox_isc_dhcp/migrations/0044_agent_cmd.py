from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("netbox_isc_dhcp", "0043_restart_req")]

    operations = [
        migrations.AddField(model_name="dhcpserver", name="agent_cmd",
                            field=models.CharField(max_length=40, blank=True, default="", help_text="Command for the agent: <start|stop|restart|update>:<id> (done once).")),
        migrations.AddField(model_name="dhcpserver", name="dhcpd_since", field=models.DateTimeField(null=True, blank=True, help_text="dhcpd running / stopped since.")),
        migrations.AddField(model_name="dhcpserver", name="dhcpd_by",
                            field=models.CharField(max_length=10, blank=True, default="", help_text="Who started/stopped dhcpd last: agent | manual.")),
    ]
