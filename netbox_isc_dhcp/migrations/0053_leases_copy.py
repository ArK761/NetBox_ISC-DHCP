from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("netbox_isc_dhcp", "0052_disk_hash")]

    operations = [
        migrations.AddField(model_name="pluginsettings", name="agent_leases_every",
                            field=models.PositiveIntegerField(default=60, help_text="Minutes between copies of the DHCP lease database on every server (0 = off).")),
        migrations.AddField(model_name="pluginsettings", name="agent_leases_keep",
                            field=models.PositiveSmallIntegerField(default=72, help_text="Lease copies kept on every server.")),
        migrations.AddField(model_name="dhcpserver", name="leases_last",
                            field=models.DateTimeField(null=True, blank=True, help_text="Last periodic copy of the lease database, as the agent reports it.")),
    ]
